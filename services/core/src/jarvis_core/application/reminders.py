"""Background delivery of due reminders."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime

import structlog

from jarvis_core.domain.ports import Notifier, ReminderRepository

log = structlog.get_logger(__name__)


class ReminderScheduler:
    """Polls for due reminders and announces them on every connected client.

    Polling (every few seconds) is deliberately simple: it survives restarts,
    sleep/wake and clock changes, and reminders set while the service was
    down are delivered as soon as it starts.

    Args:
        repo: Reminder storage.
        notifier: Broadcasts announcements to clients.
        user_name: Used to phrase the announcement.
        poll_s: Seconds between checks.
        clock: Current time provider (timezone-aware).
    """

    def __init__(
        self,
        repo: ReminderRepository,
        notifier: Notifier,
        *,
        user_name: str,
        poll_s: float = 5.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repo
        self._notifier = notifier
        #: Used to phrase announcements; updated live when the name changes.
        self.user_name = user_name
        self._poll_s = poll_s
        self._clock = clock or (lambda: datetime.now().astimezone())

    async def tick(self) -> int:
        """Deliver everything that is due; return how many reminders fired."""
        due = await self._repo.due(self._clock())
        for reminder in due:
            log.info("reminder_due", id=reminder.id, text=reminder.text)
            await self._notifier.announce(
                "reminder",
                f"Pardon the interruption, {self.user_name}. A reminder: {reminder.text}",
            )
            await self._repo.mark_delivered(reminder.id)
        if due:
            await self._notifier.data_changed("reminders")
        return len(due)

    async def run(self) -> None:
        """Poll forever (cancel the task to stop)."""
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("reminder_tick_failed")
            await asyncio.sleep(self._poll_s)
