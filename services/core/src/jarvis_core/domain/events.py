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
    ANNOUNCEMENT = "announcement"


class EnrollmentStatus(StrEnum):
    """Progress of a voice-ID enrollment."""

    RECORDING = "recording"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class StateChanged:
    """The assistant moved to a new :class:`AssistantState`."""

    state: AssistantState


@dataclass(frozen=True, slots=True)
class WakeDetected:
    """The wake phrase was heard (or the user activated the assistant manually)."""


@dataclass(frozen=True, slots=True)
class Interrupted:
    """The user cut Jarvis off; the client must stop playback immediately."""


@dataclass(frozen=True, slots=True)
class TranscriptReady:
    """The user's request, as text."""

    text: str


@dataclass(frozen=True, slots=True)
class AssistantTextDelta:
    """An incremental chunk of the assistant's written answer."""

    text: str


@dataclass(frozen=True, slots=True)
class ToolInvoked:
    """The brain is running a tool (shown as "Checking the weather…").

    Attributes:
        name: Tool name.
        label: Short present-participle phrase for the UI.
    """

    name: str
    label: str


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
class TurnMetrics:
    """Latency breakdown of one turn, in milliseconds.

    Attributes:
        stt_ms: Speech recognition time (``None`` for typed questions).
        first_token_ms: Request start → first model output.
        first_audio_ms: Request start → first answer audio ready.
        total_ms: Request start → answer fully generated.
        tools: Names of tools used during the turn.
    """

    stt_ms: float | None
    first_token_ms: float | None
    first_audio_ms: float | None
    total_ms: float
    tools: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SpeakerRejected:
    """An utterance was ignored because it did not match the enrolled voice."""

    score: float


@dataclass(frozen=True, slots=True)
class EnrollmentProgress:
    """Voice-ID enrollment progress."""

    status: EnrollmentStatus
    collected: int
    required: int


@dataclass(frozen=True, slots=True)
class Notification:
    """A proactive message (e.g. a reminder that just fired)."""

    kind: str
    text: str


@dataclass(frozen=True, slots=True)
class DataChanged:
    """Server-side data changed; widgets showing ``topic`` should refresh."""

    topic: str


@dataclass(frozen=True, slots=True)
class ErrorOccurred:
    """Something went wrong; ``message`` is safe to show to the user."""

    message: str


VoiceEvent = (
    StateChanged
    | WakeDetected
    | Interrupted
    | TranscriptReady
    | AssistantTextDelta
    | ToolInvoked
    | SpeechSegmentReady
    | TurnCompleted
    | TurnMetrics
    | SpeakerRejected
    | EnrollmentProgress
    | Notification
    | DataChanged
    | ErrorOccurred
)
