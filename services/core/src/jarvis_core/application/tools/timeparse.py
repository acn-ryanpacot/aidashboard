"""Resolve and phrase reminder times."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from jarvis_core.application.tools.registry import ToolError


def resolve_due_time(now: datetime, *, in_minutes: float | None, at: str | None) -> datetime:
    """Work out when a reminder is due.

    Args:
        now: Current local time (timezone-aware).
        in_minutes: Relative offset, e.g. ``15``.
        at: Absolute local time: ``"YYYY-MM-DDTHH:MM"`` or just ``"HH:MM"``
            (today, or tomorrow if that time has passed).

    Returns:
        A timezone-aware datetime in the future.

    Raises:
        ToolError: If neither or an unparseable/past time is given.
    """
    if in_minutes is not None:
        if in_minutes <= 0:
            raise ToolError("'in_minutes' must be positive")
        return now + timedelta(minutes=in_minutes)
    if not at:
        raise ToolError("give either 'in_minutes' or 'at'")

    text = at.strip().replace(" ", "T", 1) if "-" in at else at.strip()
    try:
        if "T" in text or "-" in text:
            due = datetime.fromisoformat(text)
            due = (
                due.replace(tzinfo=now.tzinfo) if due.tzinfo is None else due.astimezone(now.tzinfo)
            )
        else:
            clock = time.fromisoformat(text)
            due = now.replace(hour=clock.hour, minute=clock.minute, second=0, microsecond=0)
            if due <= now:
                due += timedelta(days=1)
    except ValueError as exc:
        raise ToolError(f"could not understand the time '{at}'; use YYYY-MM-DDTHH:MM") from exc

    if due <= now:
        raise ToolError("that time has already passed")
    return due


def spoken_time(when: datetime, now: datetime) -> str:
    """Phrase a time the way a person would say it.

    Example:
        "today at 3:05 PM", "tomorrow at 9 AM", "on Friday 14 November at 6:30 PM"
    """
    when = when.astimezone(now.tzinfo)
    clock = when.strftime("%I:%M %p").lstrip("0").replace(":00 ", " ")
    days = (when.date() - now.date()).days
    if days == 0:
        return f"today at {clock}"
    if days == 1:
        return f"tomorrow at {clock}"
    return f"on {when:%A} {when.day} {when:%B} at {clock}"
