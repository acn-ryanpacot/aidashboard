"""Ports: the interfaces the application layer depends on.

Each port is a :class:`typing.Protocol`, so adapters satisfy it structurally —
they never import from here, and tests can substitute simple fakes. Swapping
Ollama for another LLM, or Kokoro for another voice, means writing one new
adapter and changing one line in :mod:`jarvis_core.container`.

Blocking ports (speech models are CPU/GPU bound) are synchronous; the
application layer runs them in worker threads so the event loop stays free.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from jarvis_core.domain.events import VoiceEvent
from jarvis_core.domain.models import (
    AudioClip,
    ChatMessage,
    LlmEvent,
    SynthesizedSpeech,
    ToolSpec,
)
from jarvis_core.domain.records import (
    CalendarEvent,
    DocumentHit,
    Headline,
    KnowledgeArticle,
    MemoryRecord,
    PortfolioSnapshot,
    Reminder,
    SearchResult,
    StoredMemory,
    SystemStatus,
    Task,
    WeatherReport,
)

# ------------------------------------------------------------------- voice


class WakeWordDetector(Protocol):
    """Detects the wake phrase in a continuous stream of audio frames.

    Implementations are stateful (they keep a rolling audio window), so one
    instance is created per voice session.
    """

    def process(self, frame: bytes) -> bool:
        """Feed one 16 kHz PCM16 frame; return ``True`` when the wake phrase was heard."""
        ...

    def reset(self) -> None:
        """Clear internal buffers (call after a detection to avoid re-triggering)."""
        ...


class VoiceActivityDetector(Protocol):
    """Classifies short audio frames as speech or non-speech."""

    def is_speech(self, frame: bytes) -> bool:
        """Return ``True`` if the 16 kHz PCM16 frame contains speech."""
        ...


class SpeechToText(Protocol):
    """Transcribes a complete utterance. Blocking; run in a worker thread."""

    def transcribe(self, audio: AudioClip) -> str:
        """Return the transcript of ``audio`` (empty string if nothing intelligible)."""
        ...


class TextToSpeech(Protocol):
    """Synthesises speech with word timings. Blocking; run in a worker thread."""

    def synthesize(self, text: str) -> SynthesizedSpeech:
        """Render ``text`` to audio."""
        ...


class SpeakerEncoder(Protocol):
    """Turns an utterance into a voice embedding. Blocking; run in a worker thread."""

    def embed(self, audio: AudioClip) -> list[float]:
        """Return a fixed-length speaker embedding for ``audio``."""
        ...


class VoiceprintStore(Protocol):
    """Persists the enrolled user's reference voice embedding."""

    def load(self) -> list[float] | None:
        """Return the stored voiceprint, or ``None`` if nobody is enrolled."""
        ...

    def save(self, voiceprint: Sequence[float]) -> None:
        """Replace the stored voiceprint."""
        ...

    def clear(self) -> None:
        """Delete the stored voiceprint."""
        ...


class VoiceEventSink(Protocol):
    """Outbound port: where a voice session publishes events (e.g. a WebSocket)."""

    async def publish(self, event: VoiceEvent) -> None:
        """Deliver ``event`` to the client."""
        ...


# ------------------------------------------------------------------- brain


class LanguageModel(Protocol):
    """A chat-style language model that streams its answer and can call tools."""

    def stream_chat(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[LlmEvent]:
        """Yield the reply as :class:`TextDelta` chunks and/or :class:`ToolCall` requests."""
        ...


class EmbeddingModel(Protocol):
    """Maps text to vectors for semantic search."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding per input text."""
        ...


class Notifier(Protocol):
    """Outbound port for messages to *all* connected clients."""

    async def announce(self, kind: str, text: str) -> None:
        """Proactively tell the user something (speak it if possible)."""
        ...

    async def data_changed(self, topic: str) -> None:
        """Tell widgets showing ``topic`` to refresh."""
        ...


# -------------------------------------------------------------- repositories


class TaskRepository(Protocol):
    """Storage for :class:`~jarvis_core.domain.records.Task`."""

    async def add(self, title: str) -> Task:
        """Create an open task."""
        ...

    async def list_all(self, *, include_done: bool = False) -> list[Task]:
        """Return tasks, newest first; open ones only unless ``include_done``."""
        ...

    async def get(self, task_id: int) -> Task | None:
        """Fetch one task."""
        ...

    async def set_done(self, task_id: int, done: bool) -> Task | None:
        """Mark a task done/undone; ``None`` if it doesn't exist."""
        ...

    async def delete(self, task_id: int) -> bool:
        """Delete a task; ``False`` if it didn't exist."""
        ...


class ReminderRepository(Protocol):
    """Storage for :class:`~jarvis_core.domain.records.Reminder`."""

    async def add(self, text: str, due_at: datetime) -> Reminder:
        """Schedule a reminder."""
        ...

    async def upcoming(self) -> list[Reminder]:
        """Undelivered reminders, soonest first."""
        ...

    async def due(self, now: datetime) -> list[Reminder]:
        """Undelivered reminders whose time has come."""
        ...

    async def mark_delivered(self, reminder_id: int) -> None:
        """Record that a reminder was announced."""
        ...

    async def delete(self, reminder_id: int) -> bool:
        """Cancel a reminder."""
        ...


class MemoryStore(Protocol):
    """Storage for long-term memories and their embeddings."""

    async def add(self, text: str, embedding: Sequence[float] | None) -> MemoryRecord:
        """Store a memory."""
        ...

    async def all(self) -> list[StoredMemory]:
        """Every memory with its embedding (personal scale: hundreds, not millions)."""
        ...

    async def delete(self, memory_id: int) -> bool:
        """Forget a memory."""
        ...


# ------------------------------------------------------------- information


class WeatherProvider(Protocol):
    """Current weather lookups."""

    async def current(self, location: str) -> WeatherReport | None:
        """Weather for a place name, or ``None`` if the place is unknown."""
        ...


class KnowledgeProvider(Protocol):
    """Encyclopedic lookups."""

    async def lookup(self, topic: str) -> KnowledgeArticle | None:
        """Summary of ``topic``, or ``None`` if nothing matches."""
        ...


class WebSearchProvider(Protocol):
    """General web search."""

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Top results for ``query``."""
        ...


class DocumentSearch(Protocol):
    """Semantic search over the user's local documents."""

    async def search(self, query: str, limit: int = 4) -> list[DocumentHit]:
        """Best-matching passages for ``query``."""
        ...


class NewsProvider(Protocol):
    """Headlines from RSS/Atom feeds."""

    async def headlines(self, feeds: Sequence[str], limit: int = 10) -> list[Headline]:
        """Newest headlines across ``feeds``."""
        ...


class CalendarProvider(Protocol):
    """Events from iCalendar (ICS) sources."""

    async def events(
        self, sources: Sequence[str], start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        """Event occurrences overlapping ``[start, end)``, soonest first."""
        ...


class SystemMonitor(Protocol):
    """Host load (CPU, memory, GPU)."""

    async def status(self) -> SystemStatus:
        """Current snapshot."""
        ...


class PortfolioSource(Protocol):
    """A stock portfolio kept in another app (e.g. PisoTiyempo)."""

    async def snapshot(self) -> PortfolioSnapshot:
        """Holdings, totals and daily analyses.

        Raises:
            DataSourceUnavailableError: If the app can't be reached and has no exported data.
        """
        ...


class PreferenceStore(Protocol):
    """Small JSON documents keyed by name (UI layout, runtime settings, …)."""

    async def get(self, key: str) -> Any | None:
        """The stored value, or ``None``."""
        ...

    async def set(self, key: str, value: Any) -> None:
        """Store ``value`` (must be JSON-serialisable)."""
        ...


# ------------------------------------------------------------ capabilities


@runtime_checkable
class SupportsWarmUp(Protocol):
    """Optional capability: adapters that benefit from preloading at startup."""

    async def warm_up(self) -> None:
        """Load models / open connections so the first request is fast."""
        ...


@runtime_checkable
class SupportsModelSwitch(Protocol):
    """Optional capability: a language model whose model can change at runtime."""

    @property
    def model(self) -> str:
        """The model in use."""
        ...

    def set_model(self, model: str) -> None:
        """Switch to ``model`` for subsequent requests."""
        ...

    async def list_models(self) -> list[str]:
        """Models available to switch to."""
        ...


@runtime_checkable
class SupportsVoiceConfig(Protocol):
    """Optional capability: a TTS engine whose voice can change at runtime."""

    def configure(self, *, voice: str, speed: float) -> None:
        """Use ``voice`` at ``speed`` for subsequent synthesis."""
        ...


@runtime_checkable
class SupportsFeedUrl(Protocol):
    """Optional capability: a data source whose address can change at runtime."""

    def set_feed_url(self, url: str) -> None:
        """Read from ``url`` from now on ("" = don't use a live feed)."""
        ...


@runtime_checkable
class SupportsClose(Protocol):
    """Optional capability: adapters holding resources that must be released."""

    async def aclose(self) -> None:
        """Release resources."""
        ...
