from __future__ import annotations

from datetime import UTC, datetime

from jarvis_core.application.conversation import ConversationHistory
from jarvis_core.application.persona import Persona
from jarvis_core.domain.models import Role


def test_system_prompt_mentions_names_and_time() -> None:
    persona = Persona("Jarvis", "Ryan", "How can I help you Ryan?")
    message = persona.system_message(datetime(2026, 11, 10, 9, 30, tzinfo=UTC))
    assert message.role is Role.SYSTEM
    assert "You are Jarvis" in message.content
    assert "You serve Ryan" in message.content
    assert "Today is Tuesday, 10 November 2026, in the morning" in message.content
    assert "Markdown" in message.content


def test_prompt_prefix_is_stable_within_a_day() -> None:
    """Ollama reuses its prompt cache for an identical prefix: keep it identical."""
    persona = Persona("Jarvis", "Ryan", "How can I help you Ryan?")
    early = persona.system_message(datetime(2026, 11, 10, 9, 1, tzinfo=UTC)).content
    later = persona.system_message(
        datetime(2026, 11, 10, 11, 59, tzinfo=UTC), memories=["Ryan likes jazz"]
    ).content
    assert later.startswith(early)


def test_prompt_mentions_on_request_tools() -> None:
    persona = Persona("Jarvis", "Ryan", "How can I help you Ryan?")
    prompt = persona.system_message(tools_on_request=True).content
    assert "none are attached now" in prompt
    assert "no tools" not in prompt


def test_history_is_bounded_and_skips_blank_messages() -> None:
    history = ConversationHistory(max_messages=3)
    history.add_user("one")
    history.add_assistant("two")
    history.add_user("   ")
    history.add_user("three")
    history.add_assistant("four")
    assert [m.content for m in history.messages()] == ["two", "three", "four"]


def test_history_disabled() -> None:
    history = ConversationHistory(max_messages=0)
    history.add_user("ignored")
    assert history.messages() == []
