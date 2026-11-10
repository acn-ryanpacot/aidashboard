"""In-memory fakes for every port, so tests never load real models or hit the network."""

from __future__ import annotations

import asyncio
import zlib
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import TypeVar

from jarvis_core.application.vectors import keywords
from jarvis_core.domain.errors import LanguageModelError
from jarvis_core.domain.events import VoiceEvent
from jarvis_core.domain.models import (
    AudioClip,
    ChatMessage,
    LlmEvent,
    SynthesizedSpeech,
    TextDelta,
    ToolCall,
    ToolSpec,
    WordTiming,
)
from jarvis_core.domain.records import (
    CalendarEvent,
    DocumentHit,
    GpuStatus,
    Headline,
    KnowledgeArticle,
    SearchResult,
    SystemStatus,
    WeatherReport,
)

T = TypeVar("T")

FRAME_BYTES = 2560
SILENCE = b"\x00" * FRAME_BYTES
SPEECH = b"\x10\x27" * (FRAME_BYTES // 2)  # constant 10000 amplitude — "Ryan"
STRANGER = b"\x20\x4e" * (FRAME_BYTES // 2)  # constant 20000 amplitude — someone else
WAKE = b"\x7f\x7f" * (FRAME_BYTES // 2)  # magic frame the fake wake detector reacts to


class FakeWake:
    def __init__(self) -> None:
        self.resets = 0

    def process(self, frame: bytes) -> bool:
        return frame == WAKE

    def reset(self) -> None:
        self.resets += 1


class FakeVad:
    def is_speech(self, frame: bytes) -> bool:
        return frame in (SPEECH, WAKE, STRANGER)


class FakeStt:
    def __init__(self, transcript: str = "what time is it") -> None:
        self.transcript = transcript
        self.calls: list[AudioClip] = []

    def transcribe(self, audio: AudioClip) -> str:
        self.calls.append(audio)
        return self.transcript


Script = Sequence[str | ToolCall]


class FakeLlm:
    """Replays scripted rounds: call *n* of :meth:`stream_chat` plays ``rounds[n]``."""

    model = "fake:1b"

    def set_model(self, model: str) -> None:
        self.model = model

    async def list_models(self) -> list[str]:
        return ["fake:1b", "fake:8b"]

    def __init__(
        self,
        reply: Script = ("It is ", "noon. ", "Anything else?"),
        rounds: Sequence[Script] | None = None,
    ) -> None:
        self.rounds = list(rounds) if rounds is not None else [reply]
        self.requests: list[list[ChatMessage]] = []
        self.tool_offers: list[list[ToolSpec]] = []
        self.fail = False
        self.gate: asyncio.Event | None = None

    async def stream_chat(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[LlmEvent]:
        index = len(self.requests)
        self.requests.append(list(messages))
        self.tool_offers.append(list(tools))
        if self.fail:
            raise LanguageModelError("model offline")
        for item in self.rounds[min(index, len(self.rounds) - 1)]:
            if self.gate is not None:
                await self.gate.wait()
            yield TextDelta(item) if isinstance(item, str) else item


class FakeTts:
    SAMPLE_RATE = 24_000

    def __init__(self, seconds: float = 0.1) -> None:
        self.spoken: list[str] = []
        self.seconds = seconds

    def configure(self, *, voice: str, speed: float) -> None:
        self.voice, self.speed = voice, speed

    def synthesize(self, text: str) -> SynthesizedSpeech:
        self.spoken.append(text)
        pcm = b"\x00\x00" * int(self.SAMPLE_RATE * self.seconds)
        words = tuple(WordTiming(w, i * 0.1, i * 0.1 + 0.1) for i, w in enumerate(text.split()))
        return SynthesizedSpeech(text, AudioClip(pcm, self.SAMPLE_RATE), words)


class FakeEmbedder:
    """Bag-of-words hashing embedder: similar wording → similar vectors."""

    DIMENSIONS = 64

    def __init__(self) -> None:
        self.calls = 0
        self.fail = False

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail:
            raise LanguageModelError("embedding model missing")
        vectors = []
        for text in texts:
            vector = [0.0] * self.DIMENSIONS
            for word in keywords(text):
                vector[zlib.crc32(word.encode()) % self.DIMENSIONS] += 1.0
            vectors.append(vector)
        return vectors


class FakeSpeakerEncoder:
    """Ryan's frames embed to [1, 0]; anybody else's to [0, 1]."""

    def embed(self, audio: AudioClip) -> list[float]:
        return [1.0, 0.0] if SPEECH in audio.pcm16 else [0.0, 1.0]


class MemoryVoiceprintStore:
    def __init__(self, voiceprint: list[float] | None = None) -> None:
        self.voiceprint = voiceprint

    def load(self) -> list[float] | None:
        return self.voiceprint

    def save(self, voiceprint: Sequence[float]) -> None:
        self.voiceprint = list(voiceprint)

    def clear(self) -> None:
        self.voiceprint = None


class RecordingNotifier:
    def __init__(self) -> None:
        self.announcements: list[tuple[str, str]] = []
        self.topics: list[str] = []

    async def announce(self, kind: str, text: str) -> None:
        self.announcements.append((kind, text))

    async def data_changed(self, topic: str) -> None:
        self.topics.append(topic)


class FakeWeather:
    async def current(self, location: str) -> WeatherReport | None:
        if location.lower() == "atlantis":
            return None
        return WeatherReport(location, 21.4, 22.0, "light rain", 12.0, 80.0, 24.0, 18.0)


class FakeKnowledge:
    async def lookup(self, topic: str) -> KnowledgeArticle | None:
        if topic == "nothing":
            return None
        return KnowledgeArticle(topic.title(), f"{topic} is notable.", "https://example.org")


class FakeSearch:
    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return [SearchResult(f"Result for {query}", "snippet", "https://example.org")][:limit]


class FakeDocuments:
    async def search(self, query: str, limit: int = 4) -> list[DocumentHit]:
        return (
            [] if query == "nothing" else [DocumentHit("notes.md", "Passport expires March.", 0.9)]
        )


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[VoiceEvent] = []

    async def publish(self, event: VoiceEvent) -> None:
        self.events.append(event)

    def of_type(self, kind: type[T]) -> list[T]:
        return [e for e in self.events if isinstance(e, kind)]


class FixedClock:
    """A settable clock for time-dependent tools."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


# ------------------------------------------------------------ phase 4 fakes


class FakeNews:
    def __init__(self) -> None:
        self.calls = 0

    async def headlines(self, feeds: Sequence[str], limit: int = 10) -> list[Headline]:
        self.calls += 1
        items = [
            Headline("Mars rover finds water ice", "Space Daily", "https://example.org/1"),
            Headline("Local team wins the cup", "Sports Desk", "https://example.org/2"),
            Headline("Markets steady ahead of rate decision", "Money", "https://example.org/3"),
        ]
        return items[:limit] if feeds else []


class FakeCalendar:
    def __init__(self, events: Sequence[CalendarEvent] = ()) -> None:
        self.items = list(events)
        self.calls = 0

    async def events(
        self, sources: Sequence[str], start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        self.calls += 1
        return [e for e in self.items if e.start < end and e.end > start] if sources else []


class FakeSystem:
    async def status(self) -> SystemStatus:
        return SystemStatus(
            12.5, 7.8, 32.0, (GpuStatus("RTX Test", 40.0, 2048.0, 12288.0, 55.0),), 3600
        )


class MemoryPreferences:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}

    async def get(self, key: str) -> object | None:
        return self.data.get(key)

    async def set(self, key: str, value: object) -> None:
        self.data[key] = value
