"""The agent loop, tool registry and memory service."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest

from jarvis_core.adapters.persistence.database import Database
from jarvis_core.adapters.persistence.repositories import SqliteMemoryStore
from jarvis_core.application.brain import Brain, ToolUse
from jarvis_core.application.memory import MemoryService
from jarvis_core.application.persona import Persona, PersonaStyle
from jarvis_core.application.tools.registry import Tool, ToolError, ToolRegistry
from jarvis_core.domain.errors import JarvisError
from jarvis_core.domain.models import Role, TextDelta, ToolCall, ToolSpec
from tests.fakes import FakeEmbedder, FakeLlm

PERSONA = Persona("Jarvis", "Ryan", "How can I help you Ryan?")


def echo_tool(name: str = "echo") -> Tool:
    async def handler(args: Mapping[str, Any]) -> str:
        return f"echo:{args.get('text', '')}"

    return Tool(ToolSpec(name, "Echo text back."), "Echoing", handler)


async def collect(brain: Brain, request: str) -> list[TextDelta | ToolUse]:
    return [event async for event in brain.respond([], request)]


# ----------------------------------------------------------------- brain


async def test_plain_answer_without_tools() -> None:
    llm = FakeLlm(["Hello", " Ryan."])
    events = await collect(Brain(llm, PERSONA), "hi")
    assert events == [TextDelta("Hello"), TextDelta(" Ryan.")]
    assert llm.tool_offers == [[]]
    assert "no tools" in llm.requests[0][0].content


async def test_tool_round_trip_feeds_result_back() -> None:
    tools = ToolRegistry()
    tools.register(echo_tool())
    llm = FakeLlm(rounds=[["Let me check. "], ["Done."]])
    llm.rounds[0] = ["Let me check. ", ToolCall("echo", {"text": "ping"})]
    events = await collect(Brain(llm, PERSONA, tools), "echo ping")

    assert [e for e in events if isinstance(e, ToolUse)] == [ToolUse("echo", "Echoing")]
    second = llm.requests[1]
    assistant, tool_result = second[-2], second[-1]
    assert assistant.role is Role.ASSISTANT and assistant.content == "Let me check. "
    assert assistant.tool_calls == (ToolCall("echo", {"text": "ping"}),)
    assert (tool_result.role, tool_result.content, tool_result.tool_name) == (
        Role.TOOL,
        "echo:ping",
        "echo",
    )
    assert "You have tools" in llm.requests[0][0].content


async def test_final_round_withholds_tools() -> None:
    tools = ToolRegistry()
    tools.register(echo_tool())
    llm = FakeLlm(rounds=[[ToolCall("echo", {})], [ToolCall("echo", {})], ["Fine."]])
    await collect(Brain(llm, PERSONA, tools, max_tool_rounds=2), "loop")
    assert [len(offer) for offer in llm.tool_offers] == [1, 1, 0]


async def test_memories_are_injected_into_the_prompt() -> None:
    memory = MemoryService(SqliteMemoryStore(Database(":memory:")), FakeEmbedder(), min_score=0.3)
    await memory.remember("Ryan's favourite colour is midnight blue")
    llm = FakeLlm(["Midnight blue."])
    await collect(Brain(llm, PERSONA, None, memory), "what is my favourite colour")
    assert "midnight blue" in llm.requests[0][0].content


def test_persona_style_changes_prompt() -> None:
    formal = Persona("Jarvis", "Ryan", "", PersonaStyle("formal", "brief", "none"))
    prompt = formal.system_message(datetime(2026, 1, 1, tzinfo=UTC)).content
    assert "formal courtesy" in prompt
    assert "one or two short sentences" in prompt
    assert "Do not joke" in prompt


# -------------------------------------------------------------- registry


async def test_registry_turns_failures_into_messages() -> None:
    async def rejects(_: Mapping[str, Any]) -> str:
        raise ToolError("no such task")

    async def crashes(_: Mapping[str, Any]) -> str:
        raise RuntimeError("boom")

    async def hangs(_: Mapping[str, Any]) -> str:
        await asyncio.sleep(10)
        return "never"

    registry = ToolRegistry(timeout_s=0.05)
    registry.extend(
        [
            Tool(ToolSpec("rejects", ""), "", rejects),
            Tool(ToolSpec("crashes", ""), "", crashes),
            Tool(ToolSpec("hangs", ""), "", hangs),
        ]
    )
    assert await registry.execute(ToolCall("rejects", {})) == "Error: no such task"
    assert await registry.execute(ToolCall("crashes", {})) == "Error: the tool failed unexpectedly."
    assert "too long" in await registry.execute(ToolCall("hangs", {}))
    assert "no tool called" in await registry.execute(ToolCall("missing", {}))
    assert registry.label("missing") == "Working on it"


async def test_registry_passes_data_source_errors_to_the_model() -> None:
    async def offline(_: Mapping[str, Any]) -> str:
        raise JarvisError("Web search is unavailable right now.")

    registry = ToolRegistry()
    registry.extend([Tool(ToolSpec("offline", ""), "", offline)])
    assert await registry.execute(ToolCall("offline", {})) == (
        "Error: Web search is unavailable right now."
    )


def test_registry_rejects_duplicates() -> None:
    registry = ToolRegistry()
    registry.register(echo_tool())
    with pytest.raises(ValueError, match="Duplicate"):
        registry.register(echo_tool())
    assert "echo" in registry and len(registry) == 1


# ---------------------------------------------------------------- memory


async def test_semantic_recall_ranks_relevant_memories() -> None:
    memory = MemoryService(SqliteMemoryStore(Database(":memory:")), FakeEmbedder(), min_score=0.2)
    await memory.remember("My passport expires in March")
    await memory.remember("I prefer tea over coffee")
    found = await memory.recall("when does my passport expire")
    assert found[0].record.text == "My passport expires in March"


async def test_keyword_fallback_when_embedder_fails() -> None:
    embedder = FakeEmbedder()
    embedder.fail = True
    memory = MemoryService(SqliteMemoryStore(Database(":memory:")), embedder)
    await memory.remember("The wifi password is on the fridge")
    assert [m.record.text for m in await memory.recall("wifi password")] == [
        "The wifi password is on the fridge"
    ]
    assert await memory.relevant("unrelated words") == []
    assert embedder.calls == 1  # gave up after the first failure


async def test_forget_and_list() -> None:
    memory = MemoryService(SqliteMemoryStore(Database(":memory:")))
    record = await memory.remember("temporary")
    assert [m.text for m in await memory.all()] == ["temporary"]
    assert await memory.forget(record.id)
    assert await memory.all() == []
