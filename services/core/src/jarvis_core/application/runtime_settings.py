"""Settings the user can change from the dashboard while Jarvis is running.

``.env`` / environment variables provide the *defaults*. Changes made in the
Settings screen are stored as overrides in the ``preferences`` table and
applied live — no restart needed. See ``docs/adr/0012-runtime-settings.md``.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from jarvis_core.application.persona import Formality, Humour, Verbosity
from jarvis_core.domain.errors import JarvisError
from jarvis_core.domain.ports import PreferenceStore

log = structlog.get_logger(__name__)

PREFERENCE_KEY = "runtime_settings"

BargeIn = Literal["off", "wake_word", "voice"]
_CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class RuntimeSettings(BaseModel):
    """Everything adjustable from the Settings screen."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    # Persona
    user_name: str = Field(min_length=1, max_length=40)
    persona_formality: Formality
    persona_verbosity: Verbosity
    persona_humour: Humour
    # Voice
    tts_voice: str = Field(min_length=2, max_length=40)
    tts_speed: float = Field(gt=0.5, le=1.6)
    # Listening
    wake_threshold: float = Field(gt=0.05, lt=0.99)
    end_of_speech_ms: int = Field(ge=300, le=3000)
    listen_timeout_ms: int = Field(ge=2000, le=20000)
    follow_up_ms: int = Field(ge=0, le=30000)
    barge_in: BargeIn
    barge_in_min_speech_ms: int = Field(ge=160, le=2000)
    speaker_threshold: float = Field(ge=-1.0, le=1.0)
    # Brain
    llm_model: str = Field(min_length=1, max_length=120)
    default_location: str = Field(max_length=120)
    # Briefing & feeds
    briefing_time: str = Field(description="HH:MM local time, or empty to disable.")
    news_feeds: list[str] = Field(max_length=20)
    calendar_urls: list[str] = Field(max_length=10)
    # Companion apps
    portfolio_feed_url: str = Field(default="", max_length=200)
    # Knowledge
    documents_dir: str = Field(default="", max_length=400)

    @field_validator("documents_dir")
    @classmethod
    def _check_folder(cls, value: str) -> str:
        # Windows "Copy as path" wraps the path in quotes.
        return value.strip().strip('"').strip()

    @field_validator("portfolio_feed_url")
    @classmethod
    def _check_feed_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("use an http:// address, or leave empty to read export files only")
        return value

    @field_validator("briefing_time")
    @classmethod
    def _check_clock(cls, value: str) -> str:
        value = value.strip()
        if value and not _CLOCK.match(value):
            raise ValueError("use HH:MM (24-hour), or leave empty to disable")
        return value

    @field_validator("news_feeds", "calendar_urls")
    @classmethod
    def _check_sources(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip() for v in values if v.strip()]
        for value in cleaned:
            if not (
                value.startswith(("http://", "https://", "webcal://")) or value.endswith(".ics")
            ):
                raise ValueError(f"'{value}' is not a URL")
        return cleaned


Applier = Callable[[RuntimeSettings, RuntimeSettings], Awaitable[None] | None]


class SettingsError(JarvisError):
    """A settings update was rejected; ``message`` explains which field and why."""


class SettingsService:
    """Holds the effective :class:`RuntimeSettings` and applies changes live.

    Args:
        defaults: Values from the environment / ``.env``.
        store: Where user overrides are persisted.
    """

    def __init__(self, defaults: RuntimeSettings, store: PreferenceStore) -> None:
        self._defaults = defaults
        self._store = store
        self._current = defaults
        self._appliers: list[Applier] = []

    @property
    def current(self) -> RuntimeSettings:
        """The settings in effect right now."""
        return self._current

    @property
    def defaults(self) -> RuntimeSettings:
        """The environment defaults (what "Reset" goes back to)."""
        return self._defaults

    def on_change(self, applier: Applier) -> None:
        """Call ``applier(new, old)`` whenever settings change."""
        self._appliers.append(applier)

    async def load(self) -> RuntimeSettings:
        """Apply stored overrides (invalid stored values are skipped, not fatal)."""
        stored = await self._store.get(PREFERENCE_KEY) or {}
        try:
            merged = self._defaults.model_copy(update=self._validated(stored))
        except SettingsError as exc:
            log.warning("stored_settings_ignored", reason=str(exc))
            merged = self._defaults
        await self._switch(merged)
        return merged

    async def update(self, patch: Mapping[str, Any]) -> RuntimeSettings:
        """Validate, persist and apply a partial update.

        Raises:
            SettingsError: If any field is invalid (nothing is changed then).
        """
        changes = self._validated(patch)
        updated = self._current.model_copy(update=changes)
        overrides = {
            key: value
            for key, value in updated.model_dump().items()
            if value != getattr(self._defaults, key)
        }
        await self._store.set(PREFERENCE_KEY, overrides)
        await self._switch(updated)
        return updated

    async def reset(self) -> RuntimeSettings:
        """Drop all overrides."""
        await self._store.set(PREFERENCE_KEY, {})
        await self._switch(self._defaults)
        return self._defaults

    def _validated(self, patch: Mapping[str, Any]) -> dict[str, Any]:
        unknown = set(patch) - set(RuntimeSettings.model_fields)
        if unknown:
            raise SettingsError(f"Unknown setting(s): {', '.join(sorted(unknown))}")
        try:
            candidate = RuntimeSettings.model_validate({**self._current.model_dump(), **patch})
        except ValidationError as exc:
            first = exc.errors()[0]
            field = ".".join(str(part) for part in first["loc"])
            raise SettingsError(f"{field}: {first['msg']}") from exc
        return {key: getattr(candidate, key) for key in patch}

    async def _switch(self, new: RuntimeSettings) -> None:
        old, self._current = self._current, new
        for applier in self._appliers:
            try:
                result = applier(new, old)
                if result is not None:
                    await result
            except Exception:
                log.exception("settings_apply_failed")
        if new != old:
            changed = [
                k for k in RuntimeSettings.model_fields if getattr(new, k) != getattr(old, k)
            ]
            log.info("settings_applied", changed=changed)
