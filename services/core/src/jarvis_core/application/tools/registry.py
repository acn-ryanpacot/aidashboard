"""Tool abstraction and registry."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import structlog

from jarvis_core.domain.models import ToolCall, ToolSpec

log = structlog.get_logger(__name__)

ToolHandler = Callable[[Mapping[str, Any]], Awaitable[str]]


class ToolError(Exception):
    """A tool could not do what was asked; the message is shown to the model."""


@dataclass(frozen=True, slots=True)
class Tool:
    """A capability exposed to the language model.

    Attributes:
        spec: Name, description and JSON-schema parameters.
        label: Present-participle phrase for the UI, e.g. "Checking the weather".
        handler: Coroutine taking the parsed arguments, returning text for the model.
    """

    spec: ToolSpec
    label: str
    handler: ToolHandler

    @property
    def name(self) -> str:
        """The tool's name."""
        return self.spec.name


class ToolRegistry:
    """Holds the available tools and executes calls safely.

    Every failure mode (unknown tool, bad arguments, exceptions, timeouts) is
    turned into an ``"Error: …"`` string returned *to the model*, which can
    then apologise or try again — a broken tool never crashes a turn.

    Args:
        timeout_s: Maximum time a single tool call may take.
    """

    def __init__(self, timeout_s: float = 20.0) -> None:
        self._tools: dict[str, Tool] = {}
        self._timeout_s = timeout_s

    def register(self, tool: Tool) -> None:
        """Add a tool.

        Raises:
            ValueError: If a tool with the same name already exists.
        """
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.name}")
        self._tools[tool.name] = tool

    def extend(self, tools: Iterable[Tool]) -> None:
        """Register several tools."""
        for tool in tools:
            self.register(tool)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def specs(self) -> list[ToolSpec]:
        """Specs of every registered tool, in registration order."""
        return [tool.spec for tool in self._tools.values()]

    def label(self, name: str) -> str:
        """UI label for a tool (a generic one for unknown names)."""
        tool = self._tools.get(name)
        return tool.label if tool else "Working on it"

    async def execute(self, call: ToolCall) -> str:
        """Run a tool call and return its textual result (never raises)."""
        tool = self._tools.get(call.name)
        if tool is None:
            return f"Error: there is no tool called '{call.name}'."
        try:
            async with asyncio.timeout(self._timeout_s):
                result = await tool.handler(call.arguments)
            log.info("tool_ran", tool=call.name, arguments=dict(call.arguments))
            return result
        except ToolError as exc:
            log.info("tool_rejected", tool=call.name, reason=str(exc))
            return f"Error: {exc}"
        except TimeoutError:
            log.warning("tool_timed_out", tool=call.name)
            return "Error: the tool took too long to respond."
        except Exception:
            log.exception("tool_crashed", tool=call.name)
            return "Error: the tool failed unexpectedly."


# ------------------------------------------------------------ arg helpers


def text_arg(arguments: Mapping[str, Any], key: str, *, required: bool = True) -> str | None:
    """Read a string argument, raising :class:`ToolError` if a required one is missing."""
    value = arguments.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ToolError(f"the '{key}' argument is required")
        return None
    return str(value).strip()


def number_arg(arguments: Mapping[str, Any], key: str) -> float | None:
    """Read an optional numeric argument (models sometimes send numbers as strings)."""
    value = arguments.get(key)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"'{key}' must be a number") from exc


def schema(
    properties: Mapping[str, Mapping[str, Any]], required: Iterable[str] = ()
) -> dict[str, Any]:
    """Build a JSON-schema ``object`` for tool parameters."""
    return {"type": "object", "properties": dict(properties), "required": list(required)}
