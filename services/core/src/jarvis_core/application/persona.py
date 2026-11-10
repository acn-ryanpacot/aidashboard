"""The assistant's personality, expressed as a system prompt."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from jarvis_core.domain.models import ChatMessage, Role

Formality = Literal["formal", "balanced", "casual"]
Verbosity = Literal["brief", "balanced", "detailed"]
Humour = Literal["none", "dry", "playful"]

_FORMALITY = {
    "formal": "Speak with impeccable, formal courtesy.",
    "balanced": "Be courteous and warm, never stiff.",
    "casual": "Be relaxed and conversational, like a trusted friend.",
}
_VERBOSITY = {
    "brief": "Answer in one or two short sentences unless {user} asks for more.",
    "balanced": "Answer in one to three short sentences unless {user} asks for detail.",
    "detailed": "Give complete answers of up to six sentences when the topic warrants it.",
}
_HUMOUR = {
    "none": "Do not joke.",
    "dry": "Light, dry humour is welcome; flattery is not.",
    "playful": "Be witty and playful, but never at the expense of the answer.",
}


@dataclass(frozen=True, slots=True)
class PersonaStyle:
    """Tunable personality traits (``JARVIS_PERSONA_*`` settings)."""

    formality: Formality = "balanced"
    verbosity: Verbosity = "balanced"
    humour: Humour = "dry"


@dataclass(frozen=True, slots=True)
class Persona:
    """Who the assistant is and who it serves.

    Attributes:
        assistant_name: Name the assistant answers to.
        user_name: Name used to address the user.
        greeting: Fixed phrase spoken after the wake word.
        style: Personality traits.
    """

    assistant_name: str
    user_name: str
    greeting: str
    style: PersonaStyle = PersonaStyle()

    def system_message(
        self,
        now: datetime | None = None,
        *,
        memories: Sequence[str] = (),
        tools_available: bool = False,
    ) -> ChatMessage:
        """Build the system prompt.

        Args:
            now: Override the clock (useful for tests).
            memories: Long-term facts relevant to the current request.
            tools_available: Whether tools are offered this turn.
        """
        now = now or datetime.now().astimezone()
        user = self.user_name
        lines = [
            f"You are {self.assistant_name}, a refined and highly capable personal AI assistant "
            f"in the spirit of a British butler. You serve {user}.",
            "",
            "Your replies are converted to speech, so:",
            f"- {_VERBOSITY[self.style.verbosity].format(user=user)}",
            "- Never use Markdown, bullet points, tables, emojis, or code blocks.",
            "- Write numbers, units and symbols the way they should be spoken.",
            f"- Lead with the answer. {_FORMALITY[self.style.formality]} "
            f"{_HUMOUR[self.style.humour]}",
            "- If you do not know something, say so briefly instead of guessing.",
        ]
        if tools_available:
            lines += [
                "- You have tools for tasks, reminders, memory, weather and looking things up. "
                "Use a tool only when the request needs it, and never invent a tool's result.",
                "- When a tool returns an error, explain the problem briefly or ask a question.",
                "- Never claim abilities beyond your tools.",
            ]
        else:
            lines.append(
                "- You currently have no tools: you cannot read calendars, tasks, email or the "
                "web, control devices, or place orders. Never claim abilities you do not have."
            )
        if memories:
            lines += ["", f"Things you remember about {user}:"]
            lines += [f"- {memory}" for memory in memories]
        lines += ["", f"The current local date and time is {now:%A, %d %B %Y, %H:%M (%Z)}."]
        return ChatMessage(Role.SYSTEM, "\n".join(lines))
