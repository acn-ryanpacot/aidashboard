"""Countdown timers: parse spoken durations, ring when they reach zero.

A timer differs from a reminder in that it's about *how long*, not *when*:
"ten minutes for the rice". It shows a live countdown on the dashboard and
Jarvis says so when it's done.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from datetime import datetime, timedelta

import structlog

from jarvis_core.domain.ports import Notifier, TimerRepository
from jarvis_core.domain.records import Timer

log = structlog.get_logger(__name__)

MAX_TIMER_S = 24 * 3600
MAX_ACTIVE_TIMERS = 20

_UNIT_SECONDS = {
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
}
_UNIT = r"(?P<unit>hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)(?![a-z])"
_NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "forty five": 45,
    "fifty": 50,
    "sixty": 60,
    "ninety": 90,
}
_WORD = "|".join(sorted((re.escape(w) for w in _NUMBER_WORDS), key=len, reverse=True))
_AMOUNT = re.compile(
    rf"(?:(?P<digits>\d+(?:\.\d+)?)\s*|\b(?P<word>{_WORD})\s+){_UNIT}"
    r"(?P<half>\s+and\s+a\s+half)?"
)
_HALF = (
    (re.compile(r"\bhalf an? hour\b"), "30 minutes"),
    (re.compile(r"\bhalf a minute\b"), "30 seconds"),
    (re.compile(r"\ba quarter of an hour\b|\bquarter hour\b"), "15 minutes"),
)
_FILLER = re.compile(r"\b(set|start|a|an|the|for|timer|countdown|of|please|and)\b")


def _normalise(text: str) -> str:
    cleaned = text.lower().replace("-", " ")
    for pattern, replacement in _HALF:
        cleaned = pattern.sub(replacement, cleaned)
    return " ".join(cleaned.split())


def parse_timer_request(text: str) -> tuple[int, str]:
    """Split "12 min tea" into ``(720, "tea")``.

    Understands digits or words ("ten minutes"), several units ("1h 30m",
    "an hour and a half"), "half an hour", and a bare number as minutes.

    Raises:
        ValueError: If no positive duration is found or it is over 24 hours.
    """
    cleaned = _normalise(text)
    if re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
        seconds = round(float(cleaned) * 60)
        label = ""
    else:
        total = 0.0
        for match in _AMOUNT.finditer(cleaned):
            amount = (
                float(match["digits"]) if match["digits"] else float(_NUMBER_WORDS[match["word"]])
            )
            if match["half"]:
                amount += 0.5
            total += amount * _UNIT_SECONDS[match["unit"]]
        seconds = round(total)
        label = " ".join(_FILLER.sub(" ", _AMOUNT.sub(" ", cleaned)).split())
    if seconds <= 0:
        raise ValueError(f"no duration found in '{text}'; say e.g. '10 minutes'")
    if seconds > MAX_TIMER_S:
        raise ValueError("timers can be at most 24 hours; use a reminder for longer")
    return seconds, label


def parse_duration(text: str) -> int:
    """Seconds in a spoken duration ("10 minutes", "1h30m", "90 seconds")."""
    return parse_timer_request(text)[0]


def spoken_duration(seconds: int) -> str:
    """``1 hour 30 minutes``, ``10 minutes``, ``45 seconds``."""
    hours, rest = divmod(max(0, seconds), 3600)
    minutes, secs = divmod(rest, 60)
    parts = [
        f"{value} {unit}{'' if value == 1 else 's'}"
        for value, unit in ((hours, "hour"), (minutes, "minute"), (secs, "second"))
        if value
    ]
    return " ".join(parts) or "0 seconds"


def duration_adjective(seconds: int) -> str:
    """``10-minute``, ``1-hour 30-minute``: a duration used before a noun."""
    hours, rest = divmod(max(0, seconds), 3600)
    minutes, secs = divmod(rest, 60)
    parts = [
        f"{value}-{unit}"
        for value, unit in ((hours, "hour"), (minutes, "minute"), (secs, "second"))
        if value
    ]
    return " ".join(parts) or "0-second"


def timer_name(timer: Timer) -> str:
    """How to refer to a timer: "the rice timer" or "the 10-minute timer"."""
    if timer.label:
        label = timer.label
        return f"the {label}" if label.lower().endswith("timer") else f"the {label} timer"
    return f"the {duration_adjective(timer.duration_s)} timer"


def remaining_s(timer: Timer, now: datetime) -> int:
    """Whole seconds left (0 once it has rung)."""
    return max(0, round((timer.ends_at - now).total_seconds()))


def end_time(now: datetime, seconds: int) -> datetime:
    """When a timer started at ``now`` for ``seconds`` rings."""
    return now + timedelta(seconds=seconds)


class TimerScheduler:
    """Rings timers when they reach zero (checks every second).

    Args:
        repo: Timer storage.
        notifier: Broadcasts the announcement.
        user_name: Used to phrase it; updated live when the name changes.
        poll_s: Seconds between checks.
        clock: Current time (timezone-aware).
    """

    def __init__(
        self,
        repo: TimerRepository,
        notifier: Notifier,
        *,
        user_name: str,
        poll_s: float = 1.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repo
        self._notifier = notifier
        self.user_name = user_name
        self._poll_s = poll_s
        self._clock = clock or (lambda: datetime.now().astimezone())

    async def tick(self) -> int:
        """Ring every timer that is due; return how many rang."""
        due = await self._repo.due(self._clock())
        for timer in due:
            log.info("timer_done", id=timer.id, label=timer.label)
            name = timer_name(timer)
            await self._notifier.announce("timer", f"{self.user_name}, {name} is done.")
            await self._repo.mark_done(timer.id)
        if due:
            await self._notifier.data_changed("timers")
        return len(due)

    async def run(self) -> None:
        """Check forever (cancel the task to stop)."""
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("timer_tick_failed")
            await asyncio.sleep(self._poll_s)
