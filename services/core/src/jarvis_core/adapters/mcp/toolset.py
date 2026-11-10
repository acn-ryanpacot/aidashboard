"""Expose the tools of MCP servers as Jarvis tools.

Any `MCP <https://modelcontextprotocol.io>`_ server that speaks stdio — file
systems, calendars, home automation, Git, … — can be listed in
``JARVIS_MCP_SERVERS`` and its tools become available to the brain, named
``<server>__<tool>``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

from jarvis_core.application.tools.registry import Tool, ToolError
from jarvis_core.domain.errors import ConfigurationError
from jarvis_core.domain.models import ToolSpec

log = structlog.get_logger(__name__)

_INVALID_NAME_CHARS = re.compile(r"[^a-zA-Z0-9_]")


@dataclass(frozen=True, slots=True)
class McpServer:
    """How to launch one stdio MCP server.

    Attributes:
        name: Short identifier, used as the tool-name prefix.
        command: Executable, e.g. ``npx`` or ``uvx``.
        args: Command-line arguments.
        env: Extra environment variables.
    """

    name: str
    command: str
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)


class McpSession(Protocol):
    """The subset of ``mcp.ClientSession`` we use (lets tests inject fakes)."""

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Invoke a tool on the server."""
        ...


def tool_name(server: str, tool: str) -> str:
    """Namespaced, model-safe tool name: ``server__tool``."""
    return _INVALID_NAME_CHARS.sub("_", f"{server}__{tool}")[:64]


def result_text(result: Any) -> str:
    """Flatten an MCP ``CallToolResult`` into text for the model.

    Raises:
        ToolError: If the server flagged the result as an error.
    """
    parts = [str(getattr(item, "text", "")) for item in getattr(result, "content", []) or []]
    text = "\n".join(p for p in parts if p).strip() or "The tool returned no text."
    if getattr(result, "isError", False):
        raise ToolError(text)
    return text[:4000]


def wrap_tool(server: str, session: McpSession, remote: Any) -> Tool:
    """Adapt one MCP tool description into a :class:`Tool`."""
    remote_name = str(remote.name)
    schema = getattr(remote, "inputSchema", None) or {"type": "object", "properties": {}}

    async def handler(arguments: Mapping[str, Any]) -> str:
        return result_text(await session.call_tool(remote_name, dict(arguments)))

    return Tool(
        spec=ToolSpec(
            name=tool_name(server, remote_name),
            description=(getattr(remote, "description", "") or remote_name)[:1000],
            parameters=schema,
        ),
        label=f"Using {server}",
        handler=handler,
    )


class McpToolset:
    """Starts the configured MCP servers and collects their tools.

    Args:
        servers: Servers to launch.
    """

    def __init__(self, servers: Sequence[McpServer]) -> None:
        self._servers = servers
        self._stack = AsyncExitStack()

    async def start(self) -> list[Tool]:
        """Launch every server; servers that fail to start are skipped with a warning."""
        if not self._servers:
            return []
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ConfigurationError(
                "The MCP SDK is not installed. Run: uv sync --extra mcp"
            ) from exc

        tools: list[Tool] = []
        for server in self._servers:
            try:
                params = StdioServerParameters(
                    command=server.command, args=list(server.args), env=dict(server.env) or None
                )
                read, write = await self._stack.enter_async_context(stdio_client(params))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                listed = await session.list_tools()
                tools += [wrap_tool(server.name, session, t) for t in listed.tools]
                log.info("mcp_server_ready", server=server.name, tools=len(listed.tools))
            except Exception:
                log.warning("mcp_server_failed", server=server.name, exc_info=True)
        return tools

    async def aclose(self) -> None:
        """Shut the servers down."""
        await self._stack.aclose()
