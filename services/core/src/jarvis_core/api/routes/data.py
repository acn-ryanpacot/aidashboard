"""REST endpoints for the data Jarvis owns.

Tasks, reminders, timers, notifications, memories and voice ID.

These are what dashboard widgets read and — later — what the mobile apps sync
with. Every mutation broadcasts ``data_changed`` so all open UIs refresh.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from jarvis_core.application.hub import NOTIFICATIONS_TOPIC
from jarvis_core.application.timers import MAX_ACTIVE_TIMERS, end_time, parse_timer_request
from jarvis_core.container import Container
from jarvis_core.domain.records import MemoryRecord, NotificationRecord, Reminder, Task, Timer

router = APIRouter(prefix="/api", tags=["data"])


def _container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


# ------------------------------------------------------------------- models


class TaskOut(BaseModel):
    """A to-do item."""

    id: int
    title: str
    done: bool
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def of(cls, task: Task) -> TaskOut:
        """Build from the domain record."""
        return cls(
            id=task.id,
            title=task.title,
            done=task.done,
            created_at=task.created_at,
            completed_at=task.completed_at,
        )


class TaskIn(BaseModel):
    """Payload to create a task."""

    title: str = Field(min_length=1, max_length=300)


class TaskPatch(BaseModel):
    """Payload to complete / reopen a task."""

    done: bool


class ReminderOut(BaseModel):
    """An upcoming reminder."""

    id: int
    text: str
    due_at: datetime
    created_at: datetime

    @classmethod
    def of(cls, reminder: Reminder) -> ReminderOut:
        """Build from the domain record."""
        return cls(
            id=reminder.id,
            text=reminder.text,
            due_at=reminder.due_at,
            created_at=reminder.created_at,
        )


class ReminderIn(BaseModel):
    """Payload to create a reminder (``due_at`` must include a timezone)."""

    text: str = Field(min_length=1, max_length=300)
    due_at: datetime


class TimerOut(BaseModel):
    """A running timer (the UI counts down to ``ends_at`` itself)."""

    id: int
    label: str
    duration_s: int
    ends_at: datetime
    created_at: datetime

    @classmethod
    def of(cls, timer: Timer) -> TimerOut:
        """Build from the domain record."""
        return cls(
            id=timer.id,
            label=timer.label,
            duration_s=timer.duration_s,
            ends_at=timer.ends_at,
            created_at=timer.created_at,
        )


class TimerIn(BaseModel):
    """Payload to start a timer.

    ``duration`` is spoken-style text ("10 min", "1h30m", "12 min tea"); words
    other than the duration become the label unless ``label`` is given.
    """

    duration: str = Field(min_length=1, max_length=120)
    label: str = Field(default="", max_length=60)


class NotificationOut(BaseModel):
    """Something Jarvis announced."""

    id: int
    kind: str
    text: str
    created_at: datetime
    read: bool

    @classmethod
    def of(cls, item: NotificationRecord) -> NotificationOut:
        """Build from the domain record."""
        return cls(
            id=item.id, kind=item.kind, text=item.text, created_at=item.created_at, read=item.read
        )


class NotificationsOut(BaseModel):
    """The notifications center: recent announcements and how many are unread."""

    unread: int
    items: list[NotificationOut]


class MarkReadIn(BaseModel):
    """Which notifications to mark read (``ids`` omitted = all)."""

    ids: list[int] | None = None


class MemoryOut(BaseModel):
    """A long-term memory."""

    id: int
    text: str
    created_at: datetime

    @classmethod
    def of(cls, memory: MemoryRecord) -> MemoryOut:
        """Build from the domain record."""
        return cls(id=memory.id, text=memory.text, created_at=memory.created_at)


# -------------------------------------------------------------------- tasks


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(request: Request, include_done: bool = False) -> list[TaskOut]:
    """List tasks (open ones only unless ``include_done``)."""
    tasks = await _container(request).tasks.list_all(include_done=include_done)
    return [TaskOut.of(t) for t in tasks]


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(request: Request, body: TaskIn) -> TaskOut:
    """Create a task."""
    container = _container(request)
    task = await container.tasks.add(body.title)
    await container.hub.data_changed("tasks")
    return TaskOut.of(task)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(request: Request, task_id: int, body: TaskPatch) -> TaskOut:
    """Mark a task done or not done."""
    container = _container(request)
    task = await container.tasks.set_done(task_id, body.done)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    await container.hub.data_changed("tasks")
    return TaskOut.of(task)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(request: Request, task_id: int) -> None:
    """Delete a task."""
    container = _container(request)
    if not await container.tasks.delete(task_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    await container.hub.data_changed("tasks")


# ---------------------------------------------------------------- reminders


@router.get("/reminders", response_model=list[ReminderOut])
async def list_reminders(request: Request) -> list[ReminderOut]:
    """Upcoming (undelivered) reminders, soonest first."""
    return [ReminderOut.of(r) for r in await _container(request).reminders.upcoming()]


@router.post("/reminders", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
async def create_reminder(request: Request, body: ReminderIn) -> ReminderOut:
    """Schedule a reminder."""
    if body.due_at.tzinfo is None:
        raise HTTPException(422, "due_at needs a timezone")
    container = _container(request)
    reminder = await container.reminders.add(body.text, body.due_at)
    await container.hub.data_changed("reminders")
    return ReminderOut.of(reminder)


@router.delete("/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(request: Request, reminder_id: int) -> None:
    """Cancel a reminder."""
    container = _container(request)
    if not await container.reminders.delete(reminder_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reminder not found")
    await container.hub.data_changed("reminders")


# ------------------------------------------------------------------- timers


@router.get("/timers", response_model=list[TimerOut])
async def list_timers(request: Request) -> list[TimerOut]:
    """Running timers, soonest first."""
    return [TimerOut.of(t) for t in await _container(request).timers.active()]


@router.post("/timers", response_model=TimerOut, status_code=status.HTTP_201_CREATED)
async def create_timer(request: Request, body: TimerIn) -> TimerOut:
    """Start a timer."""
    try:
        seconds, leftover = parse_timer_request(body.duration)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    container = _container(request)
    if len(await container.timers.active()) >= MAX_ACTIVE_TIMERS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Too many timers are running")
    label = (body.label or leftover)[:60]
    timer = await container.timers.add(
        label, seconds, end_time(datetime.now().astimezone(), seconds)
    )
    await container.hub.data_changed("timers")
    return TimerOut.of(timer)


@router.delete("/timers/{timer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_timer(request: Request, timer_id: int) -> None:
    """Cancel a timer."""
    container = _container(request)
    if not await container.timers.delete(timer_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Timer not found")
    await container.hub.data_changed("timers")


# ------------------------------------------------------------ notifications


async def _notifications(container: Container, limit: int = 50) -> NotificationsOut:
    history = container.notifications
    items, unread = await history.recent(limit), await history.unread()
    return NotificationsOut(unread=len(unread), items=[NotificationOut.of(n) for n in items])


@router.get("/notifications", response_model=NotificationsOut)
async def list_notifications(
    request: Request, limit: int = Query(default=50, ge=1, le=200)
) -> NotificationsOut:
    """Recent announcements (newest first) and the unread count."""
    return await _notifications(_container(request), limit)


@router.post("/notifications/read", response_model=NotificationsOut)
async def mark_notifications_read(request: Request, body: MarkReadIn) -> NotificationsOut:
    """Mark some (or all) notifications read."""
    container = _container(request)
    if await container.notifications.mark_read(body.ids):
        await container.hub.data_changed(NOTIFICATIONS_TOPIC)
    return await _notifications(container)


@router.delete("/notifications", status_code=status.HTTP_204_NO_CONTENT)
async def clear_notifications(request: Request) -> None:
    """Delete the notification history."""
    container = _container(request)
    await container.notifications.clear()
    await container.hub.data_changed(NOTIFICATIONS_TOPIC)


# ----------------------------------------------------------------- memories


@router.get("/memories", response_model=list[MemoryOut])
async def list_memories(request: Request) -> list[MemoryOut]:
    """Everything Jarvis remembers, newest first (so you can audit it)."""
    memory = _container(request).memory
    return [MemoryOut.of(m) for m in await memory.all()] if memory else []


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(request: Request, memory_id: int) -> None:
    """Make Jarvis forget something."""
    container = _container(request)
    if container.memory is None or not await container.memory.forget(memory_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memory not found")
    await container.hub.data_changed("memories")


# ----------------------------------------------------------------- voice ID


@router.delete("/voiceprint", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voiceprint(request: Request) -> None:
    """Remove the enrolled voiceprint (Jarvis answers any voice again)."""
    container = _container(request)
    if container.speaker is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voice ID is not enabled")
    await container.speaker.clear()
    await container.hub.data_changed("voiceprint")
