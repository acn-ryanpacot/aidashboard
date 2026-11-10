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
from typing import Protocol, runtime_checkable

from jarvis_core.domain.events import VoiceEvent
from jarvis_core.domain.models import AudioClip, ChatMessage, SynthesizedSpeech


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


class LanguageModel(Protocol):
    """A chat-style language model that streams its answer."""

    def stream_chat(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        """Yield the assistant's reply as incremental text deltas."""
        ...


class TextToSpeech(Protocol):
    """Synthesises speech with word timings. Blocking; run in a worker thread."""

    def synthesize(self, text: str) -> SynthesizedSpeech:
        """Render ``text`` to audio."""
        ...


class VoiceEventSink(Protocol):
    """Outbound port: where a voice session publishes events (e.g. a WebSocket)."""

    async def publish(self, event: VoiceEvent) -> None:
        """Deliver ``event`` to the client."""
        ...


@runtime_checkable
class SupportsWarmUp(Protocol):
    """Optional capability: adapters that benefit from preloading at startup."""

    async def warm_up(self) -> None:
        """Load models / open connections so the first request is fast."""
        ...


@runtime_checkable
class SupportsClose(Protocol):
    """Optional capability: adapters holding resources that must be released."""

    async def aclose(self) -> None:
        """Release resources."""
        ...
