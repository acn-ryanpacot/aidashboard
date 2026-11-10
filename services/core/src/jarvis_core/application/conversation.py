"""Short-term conversational memory."""

from __future__ import annotations

from collections import deque

from jarvis_core.domain.models import ChatMessage, Role


class ConversationHistory:
    """A bounded window of recent user/assistant messages.

    Older messages fall off automatically so prompts stay small and fast on
    local models. Long-term memory (facts that persist across days) is a
    separate concern planned for Phase 3.

    Args:
        max_messages: How many messages to keep. ``0`` disables history.
    """

    def __init__(self, max_messages: int = 20) -> None:
        self._messages: deque[ChatMessage] = deque(maxlen=max_messages)

    def add_user(self, content: str) -> None:
        """Record something the user said."""
        self._append(ChatMessage(Role.USER, content))

    def add_assistant(self, content: str) -> None:
        """Record something the assistant said."""
        self._append(ChatMessage(Role.ASSISTANT, content))

    def messages(self) -> list[ChatMessage]:
        """Return the remembered messages, oldest first."""
        return list(self._messages)

    def clear(self) -> None:
        """Forget everything."""
        self._messages.clear()

    def _append(self, message: ChatMessage) -> None:
        if self._messages.maxlen and message.content.strip():
            self._messages.append(message)
