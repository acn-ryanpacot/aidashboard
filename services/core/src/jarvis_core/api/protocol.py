"""Wire protocol of the ``/ws/voice`` WebSocket.

Client → server
    * **Binary** frames: 80 ms of microphone audio, 16 kHz mono PCM16 LE
      (1280 samples = 2560 bytes).
    * **Text** frames: JSON :data:`ClientMessage` objects.

Server → client
    * **Text** frames: JSON :data:`ServerMessage` objects.
    * **Binary** frames: a WAV file. Each one immediately follows the
      ``speech_segment`` message that describes it.

The TypeScript mirror of these types lives in
``apps/desktop/src/core/voice/protocol.ts`` — keep them in sync.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from jarvis_core.domain.events import (
    AssistantTextDelta,
    DataChanged,
    EnrollmentProgress,
    EnrollmentStatus,
    ErrorOccurred,
    Interrupted,
    Notification,
    SegmentKind,
    SpeakerRejected,
    SpeechSegmentReady,
    StateChanged,
    ToolInvoked,
    TranscriptReady,
    TurnCompleted,
    TurnMetrics,
    VoiceEvent,
    WakeDetected,
)
from jarvis_core.domain.models import AssistantState

PROTOCOL_VERSION = 3


class _Message(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


# ------------------------------------------------------------------ client


class ActivateMessage(_Message):
    """Manually trigger the assistant (click on the orb): greet, then listen."""

    type: Literal["activate"]


class ListenMessage(_Message):
    """Push-to-talk: start listening immediately, without the greeting."""

    type: Literal["listen"]


class TextQueryMessage(_Message):
    """Ask a question by typing instead of speaking."""

    type: Literal["text_query"]
    text: str = Field(min_length=1, max_length=4000)


class PlaybackEndedMessage(_Message):
    """The client finished playing a ``speech_segment``."""

    type: Literal["playback_ended"]
    segment_id: str


class CancelMessage(_Message):
    """Stop the current answer (or enrollment) and return to idle."""

    type: Literal["cancel"]


class BargeInMessage(_Message):
    """The client's echo-aware detector heard the user talking over Jarvis."""

    type: Literal["barge_in"]


class EnrollVoiceMessage(_Message):
    """Start recording samples for voice ID."""

    type: Literal["enroll_voice"]


ClientMessage = Annotated[
    ActivateMessage
    | ListenMessage
    | TextQueryMessage
    | PlaybackEndedMessage
    | CancelMessage
    | BargeInMessage
    | EnrollVoiceMessage,
    Field(discriminator="type"),
]
client_message_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


# ------------------------------------------------------------------ server


class ReadyMessage(_Message):
    """Sent once after connecting: capabilities of this server."""

    type: Literal["ready"] = "ready"
    protocol_version: int = PROTOCOL_VERSION
    assistant_name: str
    user_name: str
    wake_word_enabled: bool
    wake_model: str | None
    speech_input_enabled: bool
    speech_output_enabled: bool
    barge_in: str
    barge_in_min_speech_ms: int
    speaker_verification_enabled: bool
    speaker_enrolled: bool
    tools: list[str]
    input_sample_rate: int
    input_frame_samples: int


class StateMessage(_Message):
    """See :class:`~jarvis_core.domain.events.StateChanged`."""

    type: Literal["state"] = "state"
    state: AssistantState


class WakeMessage(_Message):
    """See :class:`~jarvis_core.domain.events.WakeDetected`."""

    type: Literal["wake"] = "wake"


class InterruptedMessage(_Message):
    """See :class:`~jarvis_core.domain.events.Interrupted`: stop playback now."""

    type: Literal["interrupted"] = "interrupted"


class TranscriptMessage(_Message):
    """See :class:`~jarvis_core.domain.events.TranscriptReady`."""

    type: Literal["transcript"] = "transcript"
    text: str


class AssistantDeltaMessage(_Message):
    """See :class:`~jarvis_core.domain.events.AssistantTextDelta`."""

    type: Literal["assistant_delta"] = "assistant_delta"
    text: str


class ToolMessage(_Message):
    """See :class:`~jarvis_core.domain.events.ToolInvoked`."""

    type: Literal["tool"] = "tool"
    name: str
    label: str


class WordTimingModel(_Message):
    """Timing of one spoken word, in seconds from the start of the segment."""

    word: str
    start: float
    end: float


class SpeechSegmentMessage(_Message):
    """Header for the WAV binary frame that follows it."""

    type: Literal["speech_segment"] = "speech_segment"
    segment_id: str
    kind: SegmentKind
    text: str
    duration: float
    words: list[WordTimingModel]


class TurnCompleteMessage(_Message):
    """See :class:`~jarvis_core.domain.events.TurnCompleted`."""

    type: Literal["turn_complete"] = "turn_complete"
    text: str


class MetricsMessage(_Message):
    """See :class:`~jarvis_core.domain.events.TurnMetrics` (milliseconds)."""

    type: Literal["metrics"] = "metrics"
    stt_ms: float | None
    first_token_ms: float | None
    first_audio_ms: float | None
    total_ms: float
    tools: list[str]


class SpeakerRejectedMessage(_Message):
    """See :class:`~jarvis_core.domain.events.SpeakerRejected`."""

    type: Literal["speaker_rejected"] = "speaker_rejected"
    score: float


class EnrollmentMessage(_Message):
    """See :class:`~jarvis_core.domain.events.EnrollmentProgress`."""

    type: Literal["enrollment"] = "enrollment"
    status: EnrollmentStatus
    collected: int
    required: int


class NotificationMessage(_Message):
    """See :class:`~jarvis_core.domain.events.Notification`."""

    type: Literal["notification"] = "notification"
    kind: str
    text: str


class DataChangedMessage(_Message):
    """See :class:`~jarvis_core.domain.events.DataChanged`."""

    type: Literal["data_changed"] = "data_changed"
    topic: str


class ErrorMessage(_Message):
    """See :class:`~jarvis_core.domain.events.ErrorOccurred`."""

    type: Literal["error"] = "error"
    message: str


ServerMessage = (
    ReadyMessage
    | StateMessage
    | WakeMessage
    | InterruptedMessage
    | TranscriptMessage
    | AssistantDeltaMessage
    | ToolMessage
    | SpeechSegmentMessage
    | TurnCompleteMessage
    | MetricsMessage
    | SpeakerRejectedMessage
    | EnrollmentMessage
    | NotificationMessage
    | DataChangedMessage
    | ErrorMessage
)


def to_server_message(event: VoiceEvent) -> ServerMessage:
    """Map a domain event to its JSON wire representation."""
    match event:
        case StateChanged(state=state):
            return StateMessage(state=state)
        case WakeDetected():
            return WakeMessage()
        case Interrupted():
            return InterruptedMessage()
        case TranscriptReady(text=text):
            return TranscriptMessage(text=text)
        case AssistantTextDelta(text=text):
            return AssistantDeltaMessage(text=text)
        case ToolInvoked(name=name, label=label):
            return ToolMessage(name=name, label=label)
        case SpeechSegmentReady(segment_id=segment_id, kind=kind, speech=speech):
            return SpeechSegmentMessage(
                segment_id=segment_id,
                kind=kind,
                text=speech.text,
                duration=round(speech.audio.duration_seconds, 3),
                words=[
                    WordTimingModel(word=w.word, start=w.start, end=w.end) for w in speech.words
                ],
            )
        case TurnCompleted(text=text):
            return TurnCompleteMessage(text=text)
        case TurnMetrics() as m:
            return MetricsMessage(
                stt_ms=m.stt_ms,
                first_token_ms=m.first_token_ms,
                first_audio_ms=m.first_audio_ms,
                total_ms=m.total_ms,
                tools=list(m.tools),
            )
        case SpeakerRejected(score=score):
            return SpeakerRejectedMessage(score=score)
        case EnrollmentProgress(status=status, collected=collected, required=required):
            return EnrollmentMessage(status=status, collected=collected, required=required)
        case Notification(kind=kind, text=text):
            return NotificationMessage(kind=kind, text=text)
        case DataChanged(topic=topic):
            return DataChangedMessage(topic=topic)
        case ErrorOccurred(message=message):
            return ErrorMessage(message=message)
    raise TypeError(f"Unhandled event type: {type(event).__name__}")  # pragma: no cover
