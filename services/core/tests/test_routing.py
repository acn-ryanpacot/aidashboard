"""Per-request tool routing."""

from __future__ import annotations

import pytest

from jarvis_core.adapters.persistence.database import Database
from jarvis_core.adapters.persistence.repositories import (
    SqliteMemoryStore,
    SqliteReminderRepository,
    SqliteTaskRepository,
)
from jarvis_core.application.brain import Brain
from jarvis_core.application.information import NewsService
from jarvis_core.application.memory import MemoryService
from jarvis_core.application.persona import Persona
from jarvis_core.application.tools import builtin
from jarvis_core.application.tools.registry import ToolRegistry
from jarvis_core.application.tools.routing import BUILTIN_GROUPS, ToolRouter, mcp_group
from jarvis_core.domain.models import ChatMessage, Role, ToolSpec
from tests.fakes import (
    FakeDocuments,
    FakeEmbedder,
    FakeKnowledge,
    FakeLlm,
    FakeNews,
    FakeSearch,
    FakeWeather,
)


def full_registry() -> ToolRegistry:
    db = Database(":memory:")
    registry = ToolRegistry()
    registry.extend(builtin.time_tools())
    registry.extend(builtin.task_tools(SqliteTaskRepository(db)))
    registry.extend(builtin.reminder_tools(SqliteReminderRepository(db)))
    registry.extend(builtin.memory_tools(MemoryService(SqliteMemoryStore(db))))
    registry.extend(builtin.weather_tools(FakeWeather()))
    registry.extend(builtin.knowledge_tools(FakeKnowledge()))
    registry.extend(builtin.web_search_tools(FakeSearch()))
    registry.extend(builtin.document_tools(FakeDocuments()))
    registry.extend(builtin.news_tools(NewsService(FakeNews(), lambda: ["https://f"])))
    return registry


SPECS = full_registry().specs()


async def routed(request: str, previous: str | None = None, **kwargs: object) -> set[str]:
    router = ToolRouter(**kwargs)  # type: ignore[arg-type]
    return {spec.name for spec in await router.select(request, SPECS, previous)}


def test_every_builtin_tool_belongs_to_exactly_one_group() -> None:
    for spec in SPECS:
        owners = [g.name for g in BUILTIN_GROUPS if g.owns(spec.name)]
        assert len(owners) == 1, (spec.name, owners)


@pytest.mark.parametrize(
    ("request_text", "expected"),
    [
        ("Add buy milk to my tasks", {"add_task", "list_tasks", "complete_task"}),
        ("Put eggs on the shopping list", {"add_task", "list_tasks", "complete_task"}),
        (
            "Remind me to stretch in 10 minutes",
            {"set_reminder", "list_reminders", "cancel_reminder"},
        ),
        ("What's the weather in Tokyo?", {"get_weather"}),
        ("Will it rain today?", {"get_weather"}),
        ("What time is it?", {"get_current_time"}),
        ("Remember that my passport expires in March", {"remember", "recall", "forget"}),
        ("Who was Ada Lovelace?", {"lookup_encyclopedia"}),
        ("Any news about the Mars mission?", {"get_headlines"}),
        ("Search the web for the latest Mars mission", {"web_search"}),
        ("What did I write in my notes about the budget?", {"search_documents"}),
    ],
)
async def test_keyword_routing(request_text: str, expected: set[str]) -> None:
    assert await routed(request_text) == expected


@pytest.mark.parametrize(
    "request_text",
    [
        "Tell me a fun fact about owls",
        "Hello Jarvis, how are you?",
        "Explain recursion like I'm five",
    ],
)
async def test_chit_chat_gets_no_tools(request_text: str) -> None:
    assert await routed(request_text) == set()


async def test_vague_follow_up_inherits_previous_topic() -> None:
    assert await routed("and call dad too", previous="add call mum to my tasks") == {
        "add_task",
        "list_tasks",
        "complete_task",
    }


async def test_new_topic_does_not_drag_in_the_previous_one() -> None:
    assert await routed("what's the weather in Oslo", previous="mark buy milk done") == {
        "get_weather"
    }


async def test_max_tools_cap() -> None:
    assert len(await routed("remind me about my tasks and the weather", max_tools=4)) == 4


async def test_embedding_fallback_picks_best_group() -> None:
    router = ToolRouter(embedder=FakeEmbedder(), min_similarity=0.2)
    names = {s.name for s in await router.select("forecast humidity outdoors tomorrow", SPECS)}
    assert names == {"get_weather"}


async def test_embedding_failure_degrades_to_no_tools() -> None:
    embedder = FakeEmbedder()
    embedder.fail = True
    router = ToolRouter(embedder=embedder)
    assert await router.select("something unusual", SPECS) == []
    assert await router.select("something else", SPECS) == []
    assert embedder.calls == 1


async def test_mcp_groups_route_by_server_and_tool_words() -> None:
    specs = [
        ToolSpec("homeassistant__turn_on_light", ""),
        ToolSpec("homeassistant__set_thermostat", ""),
    ]
    router = ToolRouter(groups=())
    router.add_group(mcp_group("homeassistant", specs))
    assert {s.name for s in await router.select("set the thermostat to 21", specs)} == {
        "homeassistant__turn_on_light",
        "homeassistant__set_thermostat",
    }
    assert await router.select("tell me a joke", specs) == []


async def test_brain_attaches_only_routed_tools() -> None:
    llm = FakeLlm(["Done."])
    brain = Brain(llm, Persona("Jarvis", "Ryan", ""), full_registry(), router=ToolRouter())
    _ = [e async for e in brain.respond([], "What's the weather like?")]
    _ = [e async for e in brain.respond([], "Tell me a fun fact about owls")]
    assert [{s.name for s in offer} for offer in llm.tool_offers] == [{"get_weather"}, set()]
    assert "none are attached now" in llm.requests[1][0].content


async def test_brain_uses_previous_user_message_for_routing() -> None:
    llm = FakeLlm(["Done."])
    brain = Brain(llm, Persona("Jarvis", "Ryan", ""), full_registry(), router=ToolRouter())
    history = [
        ChatMessage(Role.USER, "Add call the bank to my tasks"),
        ChatMessage(Role.ASSISTANT, "Added."),
    ]
    _ = [e async for e in brain.respond(history, "Actually, mark it done")]
    assert "complete_task" in {s.name for s in llm.tool_offers[0]}
