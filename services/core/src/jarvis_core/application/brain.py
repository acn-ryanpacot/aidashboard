"""The brain: an agent loop over the language model, tools and memory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

import structlog

from jarvis_core.application.memory import MemoryService
from jarvis_core.application.persona import Persona
from jarvis_core.application.tools.registry import ToolRegistry
from jarvis_core.domain.models import ChatMessage, Role, TextDelta, ToolCall
from jarvis_core.domain.ports import LanguageModel

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ToolUse:
    """Yielded by :meth:`Brain.respond` just before a tool runs."""

    name: str
    label: str


BrainEvent = TextDelta | ToolUse


class Brain:
    """Answers a request, calling tools as often as the model needs.

    The loop::

        prompt = persona + relevant memories + history + request
        repeat (≤ max_tool_rounds):
            stream the model's reply  → text is yielded immediately
            if it asked for tools     → run them, append results, go again
            else                      → done
        final round: tools are withheld so the model must answer in words

    Args:
        llm: Any :class:`~jarvis_core.domain.ports.LanguageModel`.
        persona: Identity and style.
        tools: Available tools (``None`` or empty = plain chat).
        memory: Long-term memory injected into the prompt.
        max_tool_rounds: Upper bound on model ↔ tool round trips per turn.
    """

    def __init__(
        self,
        llm: LanguageModel,
        persona: Persona,
        tools: ToolRegistry | None = None,
        memory: MemoryService | None = None,
        *,
        max_tool_rounds: int = 4,
    ) -> None:
        self._llm = llm
        self._persona = persona
        self._tools = tools
        self._memory = memory
        self._max_tool_rounds = max_tool_rounds

    @property
    def persona(self) -> Persona:
        """The persona in use."""
        return self._persona

    async def respond(
        self, history: Sequence[ChatMessage], request: str
    ) -> AsyncIterator[BrainEvent]:
        """Stream the answer to ``request`` given prior ``history``."""
        # Tools may be added after start-up (MCP servers), so check per turn.
        tools = self._tools if self._tools is not None and len(self._tools) > 0 else None
        memories = await self._memory.relevant(request) if self._memory else []
        messages: list[ChatMessage] = [
            self._persona.system_message(memories=memories, tools_available=tools is not None),
            *history,
            ChatMessage(Role.USER, request),
        ]
        specs = tools.specs() if tools else []

        for round_number in range(self._max_tool_rounds + 1):
            offered = specs if round_number < self._max_tool_rounds else []
            calls: list[ToolCall] = []
            text_parts: list[str] = []
            async for event in self._llm.stream_chat(messages, offered):
                if isinstance(event, TextDelta):
                    text_parts.append(event.text)
                    yield event
                else:
                    calls.append(event)
            if not calls or tools is None:
                return

            messages.append(ChatMessage(Role.ASSISTANT, "".join(text_parts), tuple(calls)))
            for call in calls:
                yield ToolUse(call.name, tools.label(call.name))
                result = await tools.execute(call)
                messages.append(ChatMessage(Role.TOOL, result, tool_name=call.name))
        log.warning("tool_round_limit_reached", rounds=self._max_tool_rounds)  # pragma: no cover
