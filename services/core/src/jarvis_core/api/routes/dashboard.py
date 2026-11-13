"""REST endpoints behind the dashboard.

Live settings, UI preferences, weather, news, calendar and system status.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi import Path as PathParam
from pydantic import BaseModel

from jarvis_core.api.auth import request_is_local
from jarvis_core.application.runtime_settings import RuntimeSettings, SettingsError
from jarvis_core.container import Container
from jarvis_core.domain.errors import JarvisError
from jarvis_core.domain.ports import SupportsModelSwitch

router = APIRouter(prefix="/api", tags=["dashboard"])

#: UI preference documents are stored under this namespace (never collide with
#: internal keys such as runtime settings).
UI_PREFIX = "ui:"
UI_KEY_PATTERN = r"^[a-z][a-z0-9_-]{0,40}$"
MAX_UI_DOCUMENT_BYTES = 64 * 1024


def _container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


# ---------------------------------------------------------------- settings


class SettingsResponse(BaseModel):
    """Effective settings, their environment defaults, and choices for the UI."""

    values: RuntimeSettings
    defaults: RuntimeSettings


class VoiceOption(BaseModel):
    """A selectable text-to-speech voice."""

    id: str
    label: str


class ModelsResponse(BaseModel):
    """Language models available in Ollama."""

    current: str
    available: list[str]


def _settings_response(container: Container) -> SettingsResponse:
    return SettingsResponse(values=container.runtime.current, defaults=container.runtime.defaults)


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(request: Request) -> SettingsResponse:
    """Current settings and their defaults."""
    return _settings_response(_container(request))


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    request: Request, patch: dict[str, Any] = Body(..., examples=[{"tts_voice": "bm_lewis"}])
) -> SettingsResponse:
    """Change some settings; they apply immediately, no restart needed.

    The documents folder can only be changed on the PC itself: a paired phone
    must not be able to point Jarvis at another folder of yours.
    """
    container = _container(request)
    if (
        "documents_dir" in patch
        and str(patch["documents_dir"]).strip().strip('"').strip()
        != container.runtime.current.documents_dir
        and not request_is_local(request)
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Change the documents folder on the PC itself."
        )
    try:
        await container.runtime.update(patch)
    except SettingsError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _settings_response(container)


@router.post("/settings/reset", response_model=SettingsResponse)
async def reset_settings(request: Request) -> SettingsResponse:
    """Go back to the values from ``.env``."""
    container = _container(request)
    await container.runtime.reset()
    return _settings_response(container)


@router.get("/voices", response_model=list[VoiceOption])
async def list_voices() -> list[VoiceOption]:
    """Kokoro voices offered in Settings."""
    from jarvis_core.adapters.tts.kokoro import KOKORO_VOICES

    return [VoiceOption(id=key, label=label) for key, (label, _) in KOKORO_VOICES.items()]


@router.get("/models", response_model=ModelsResponse)
async def list_models(request: Request) -> ModelsResponse:
    """Installed Ollama models (to pick from in Settings)."""
    container = _container(request)
    llm = container.llm
    available = await llm.list_models() if isinstance(llm, SupportsModelSwitch) else []
    current = container.runtime.current.llm_model
    return ModelsResponse(current=current, available=sorted(set(available) | {current}))


# ---------------------------------------------------------- UI preferences


@router.get("/ui-preferences/{key}")
async def get_ui_preference(request: Request, key: str = PathParam(pattern=UI_KEY_PATTERN)) -> Any:
    """A UI document (e.g. the dashboard ``layout``); ``null`` if never saved."""
    return await _container(request).preferences.get(UI_PREFIX + key)


@router.put("/ui-preferences/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def put_ui_preference(
    request: Request,
    key: str = PathParam(pattern=UI_KEY_PATTERN),
    value: Any = Body(...),
) -> None:
    """Store a UI document (max 64 KB)."""
    container = _container(request)
    if len(await request.body()) > MAX_UI_DOCUMENT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Document too large")
    await container.preferences.set(UI_PREFIX + key, value)
    await container.hub.data_changed(f"ui:{key}")


# ------------------------------------------------------------- information


class WeatherOut(BaseModel):
    """Current conditions."""

    location: str
    temperature_c: float
    feels_like_c: float
    description: str
    wind_kph: float
    humidity_pct: float
    high_c: float | None
    low_c: float | None


class HeadlineOut(BaseModel):
    """A news headline."""

    title: str
    source: str
    url: str
    published: datetime | None


class EventOut(BaseModel):
    """A calendar event occurrence."""

    title: str
    start: datetime
    end: datetime
    all_day: bool
    location: str
    calendar: str


class CalendarOut(BaseModel):
    """Events plus whether any calendar is connected at all."""

    configured: bool
    events: list[EventOut]


class GpuOut(BaseModel):
    """One GPU's load."""

    name: str
    utilization_pct: float
    memory_used_mb: float
    memory_total_mb: float
    temperature_c: float | None


class SystemOut(BaseModel):
    """Host load."""

    cpu_percent: float
    memory_used_gb: float
    memory_total_gb: float
    gpus: list[GpuOut]
    uptime_s: float


@router.get("/weather", response_model=WeatherOut | None)
async def get_weather(request: Request, location: str = "") -> WeatherOut | None:
    """Weather at ``location`` (default: the home location from Settings)."""
    service = _container(request).weather
    if service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Weather is disabled")
    try:
        report = await service.current(location)
    except JarvisError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return WeatherOut(**asdict(report)) if report is not None else None


@router.get("/news", response_model=list[HeadlineOut])
async def get_news(
    request: Request, limit: int = Query(default=8, ge=1, le=30)
) -> list[HeadlineOut]:
    """Latest headlines from the configured feeds."""
    service = _container(request).news
    if service is None:
        return []
    return [HeadlineOut(**asdict(h)) for h in await service.headlines(limit)]


@router.get("/calendar", response_model=CalendarOut)
async def get_calendar(request: Request, days: int = Query(default=2, ge=1, le=31)) -> CalendarOut:
    """Upcoming events (today plus ``days - 1`` more days)."""
    service = _container(request).schedule
    if service is None or not service.configured:
        return CalendarOut(configured=False, events=[])
    now = datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    events = await service.between(start, start + timedelta(days=days))
    return CalendarOut(
        configured=True, events=[EventOut(**asdict(e)) for e in events if e.end > now]
    )


@router.get("/system", response_model=SystemOut)
async def get_system(request: Request) -> SystemOut:
    """CPU, RAM and GPU load of the machine running the core service."""
    monitor = _container(request).system
    if monitor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "System monitor is disabled")
    snapshot = await monitor.status()
    return SystemOut(
        cpu_percent=snapshot.cpu_percent,
        memory_used_gb=snapshot.memory_used_gb,
        memory_total_gb=snapshot.memory_total_gb,
        gpus=[GpuOut(**asdict(g)) for g in snapshot.gpus],
        uptime_s=snapshot.uptime_s,
    )
