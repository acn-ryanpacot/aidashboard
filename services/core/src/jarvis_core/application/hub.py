"""Fan-out to every connected voice session."""

from __future__ import annotations

import structlog

from jarvis_core.application.voice_session import VoiceSession
from jarvis_core.domain.events import DataChanged
from jarvis_core.domain.ports import NotificationRepository, VoiceEventSink

log = structlog.get_logger(__name__)

#: ``data_changed`` topic for the notifications center.
NOTIFICATIONS_TOPIC = "notifications"


class SessionHub:
    """Tracks live sessions and implements :class:`~jarvis_core.domain.ports.Notifier`.

    Used by background jobs (reminders, timers, alerts, the briefing) and REST
    endpoints to reach clients: announcements are spoken by each idle session,
    and ``data_changed`` tells widgets to refetch.

    Args:
        history: Where every announcement is recorded for the notifications
            center, including ones made while no window was open.
    """

    def __init__(self, history: NotificationRepository | None = None) -> None:
        self._sessions: dict[VoiceSession, VoiceEventSink] = {}
        self._history = history

    def __len__(self) -> int:
        return len(self._sessions)

    def sessions(self) -> list[VoiceSession]:
        """The currently connected sessions."""
        return list(self._sessions)

    def register(self, session: VoiceSession, sink: VoiceEventSink) -> None:
        """Start delivering broadcasts to ``session``."""
        self._sessions[session] = sink

    def unregister(self, session: VoiceSession) -> None:
        """Stop delivering broadcasts to ``session``."""
        self._sessions.pop(session, None)

    async def announce(self, kind: str, text: str) -> None:
        """Record ``text`` and have every session say it (or show it, if it can't speak)."""
        if self._history is not None:
            try:
                await self._history.add(kind, text)
            except Exception:
                log.warning("notification_record_failed", exc_info=True)
        if not self._sessions:
            log.info("announcement_without_clients", kind=kind, text=text)
        for session in list(self._sessions):
            try:
                await session.announce(kind, text)
            except Exception:
                log.warning("announce_failed", exc_info=True)
        if self._history is not None:
            await self.data_changed(NOTIFICATIONS_TOPIC)

    async def data_changed(self, topic: str) -> None:
        """Tell every client that ``topic`` data changed."""
        for sink in list(self._sessions.values()):
            try:
                await sink.publish(DataChanged(topic))
            except Exception:
                log.debug("data_changed_delivery_failed", exc_info=True)
