"""The assistant's personality, expressed as a system prompt."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from jarvis_core.domain.models import ChatMessage, Role


@dataclass(frozen=True, slots=True)
class Persona:
    """Who the assistant is and who it serves.

    Attributes:
        assistant_name: Name the assistant answers to.
        user_name: Name used to address the user.
        greeting: Fixed phrase spoken after the wake word.
    """

    assistant_name: str
    user_name: str
    greeting: str

    def system_message(self, now: datetime | None = None) -> ChatMessage:
        """Build the system prompt, including the current local date and time.

        Args:
            now: Override the clock (useful for tests).
        """
        now = now or datetime.now().astimezone()
        prompt = f"""\
You are {self.assistant_name}, a refined, witty and highly capable personal AI \
assistant in the spirit of a British butler. You serve {self.user_name}.

Your replies are converted to speech, so:
- Answer in one to three short, natural sentences unless {self.user_name} asks for detail.
- Never use Markdown, bullet points, tables, emojis, or code blocks.
- Write numbers, units and symbols the way they should be spoken.
- Be direct; lead with the answer. Light dry humour is welcome, flattery is not.
- If you do not know something or lack live data, say so briefly instead of guessing.
- You currently have no tools: you cannot read calendars, tasks, email or the web, \
control devices, or place orders. Never claim or offer abilities you do not have.

The current local date and time is {now:%A, %d %B %Y, %H:%M (%Z)}."""
        return ChatMessage(Role.SYSTEM, prompt)
