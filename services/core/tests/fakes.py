"""In-memory fakes for every port, so tests never load real models."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import TypeVar

from jarvis_core.domain.errors import LanguageModelError
from jarvis_core.domain.events import VoiceEvent
from jarvis_core.domain.models import AudioClip, ChatMessage, SynthesizedSpeech, WordTiming

T = TypeVar("T")

FRAME_BYTES = 2560
SILENCE = b"\x00" * FRAME_BYTES
SPEECH = b"\x10\x27" * (FRAME_BYTES // 2)  # constant 10000 amplitude
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
        return frame in (SPEECH, WAKE)


class FakeStt:
    def __init__(self, transcript: str = "what time is it") -> None:
        self.transcript = transcript
        self.calls: list[AudioClip] = []

    def transcribe(self, audio: AudioClip) -> str:
        self.calls.append(audio)
        return self.transcript


class FakeLlm:
    def __init__(self, reply: Sequence[str] = ("It is ", "noon. ", "Anything else?")) -> None:
        self.reply = list(reply)
        self.requests: list[list[ChatMessage]] = []
        self.fail = False
        self.gate: asyncio.Event | None = None

    async def stream_chat(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        self.requests.append(list(messages))
        if self.fail:
            raise LanguageModelError("model offline")
        for delta in self.reply:
            if self.gate is not None:
                await self.gate.wait()
            yield delta


class FakeTts:
    SAMPLE_RATE = 24_000

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def synthesize(self, text: str) -> SynthesizedSpeech:
        self.spoken.append(text)
        pcm = b"\x00\x00" * (self.SAMPLE_RATE // 10)  # 100 ms
        words = tuple(WordTiming(w, i * 0.1, i * 0.1 + 0.1) for i, w in enumerate(text.split()))
        return SynthesizedSpeech(text, AudioClip(pcm, self.SAMPLE_RATE), words)


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[VoiceEvent] = []

    async def publish(self, event: VoiceEvent) -> None:
        self.events.append(event)

    def of_type(self, kind: type[T]) -> list[T]:
        return [e for e in self.events if isinstance(e, kind)]
