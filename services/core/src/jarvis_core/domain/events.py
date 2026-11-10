"""Events emitted by a voice session.

These are transport-agnostic; :mod:`jarvis_core.api.protocol` maps them onto
WebSocket messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from jarvis_core.domain.models import AssistantState, SynthesizedSpeech


class SegmentKind(StrEnum):
    """Why a speech segment is being played."""

    GREETING = "greeting"
    ANSWER = "answer"


@dataclass(frozen=True, slots=True)
class StateChanged:
    """The assistant moved to a new :class:`AssistantState`."""

    state: AssistantState


@dataclass(frozen=True, slots=True)
class WakeDetected:
    """The wake phrase was heard (or the user activated the assistant manually)."""


@dataclass(frozen=True, slots=True)
class TranscriptReady:
    """The user's request, as text."""

    text: str


@dataclass(frozen=True, slots=True)
class AssistantTextDelta:
    """An incremental chunk of the assistant's written answer."""

    text: str


@dataclass(frozen=True, slots=True)
class SpeechSegmentReady:
    """A sentence of synthesised speech is ready for playback.

    The client must reply with a ``playback_ended`` message carrying
    ``segment_id`` once the audio has finished playing.
    """

    segment_id: str
    kind: SegmentKind
    speech: SynthesizedSpeech


@dataclass(frozen=True, slots=True)
class TurnCompleted:
    """The assistant has finished generating its answer."""

    text: str


@dataclass(frozen=True, slots=True)
class ErrorOccurred:
    """Something went wrong; ``message`` is safe to show to the user."""

    message: str


VoiceEvent = (
    StateChanged
    | WakeDetected
    | TranscriptReady
    | AssistantTextDelta
    | SpeechSegmentReady
    | TurnCompleted
    | ErrorOccurred
)
