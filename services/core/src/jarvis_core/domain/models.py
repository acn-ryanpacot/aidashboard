"""Core value objects shared across the voice pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

#: Sample rate of microphone audio streamed from the client (Hz).
INPUT_SAMPLE_RATE = 16_000
#: Samples per client audio frame (80 ms at 16 kHz — what openWakeWord expects).
INPUT_FRAME_SAMPLES = 1_280
#: Bytes per sample for 16-bit PCM.
PCM16_SAMPLE_WIDTH = 2


class AssistantState(StrEnum):
    """What the assistant is doing right now. Drives the UI orb animation."""

    IDLE = "idle"
    """Waiting for the wake word."""
    LISTENING = "listening"
    """Recording the user's request."""
    THINKING = "thinking"
    """Transcribing and generating an answer."""
    SPEAKING = "speaking"
    """Audio is being played back on the client."""


class Role(StrEnum):
    """Author of a chat message, using the common LLM chat convention."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A single message in a conversation with the language model."""

    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class AudioClip:
    """Mono, 16-bit little-endian PCM audio.

    Attributes:
        pcm16: Raw sample bytes.
        sample_rate: Samples per second.
    """

    pcm16: bytes
    sample_rate: int

    @property
    def sample_count(self) -> int:
        """Number of samples in the clip."""
        return len(self.pcm16) // PCM16_SAMPLE_WIDTH

    @property
    def duration_seconds(self) -> float:
        """Length of the clip in seconds."""
        return self.sample_count / self.sample_rate if self.sample_rate else 0.0


@dataclass(frozen=True, slots=True)
class WordTiming:
    """When a word is spoken within a :class:`SynthesizedSpeech` clip.

    Attributes:
        word: The word as displayed in captions.
        start: Offset from the start of the clip, in seconds.
        end: Offset from the start of the clip, in seconds.
    """

    word: str
    start: float
    end: float


@dataclass(frozen=True, slots=True)
class SynthesizedSpeech:
    """Output of a text-to-speech engine: audio plus per-word timings for captions."""

    text: str
    audio: AudioClip
    words: tuple[WordTiming, ...] = field(default_factory=tuple)
