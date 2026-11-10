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
    ErrorOccurred,
    SegmentKind,
    SpeechSegmentReady,
    StateChanged,
    TranscriptReady,
    TurnCompleted,
    VoiceEvent,
    WakeDetected,
)
from jarvis_core.domain.models import AssistantState

PROTOCOL_VERSION = 1


class _Message(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


# ------------------------------------------------------------------ client


class ActivateMessage(_Message):
    """Manually trigger the assistant (click on the orb / push-to-talk)."""

    type: Literal["activate"]


class TextQueryMessage(_Message):
    """Ask a question by typing instead of speaking."""

    type: Literal["text_query"]
    text: str = Field(min_length=1, max_length=4000)


class PlaybackEndedMessage(_Message):
    """The client finished playing a ``speech_segment``."""

    type: Literal["playback_ended"]
    segment_id: str


class CancelMessage(_Message):
    """Stop the current answer and return to idle."""

    type: Literal["cancel"]


ClientMessage = Annotated[
    ActivateMessage | TextQueryMessage | PlaybackEndedMessage | CancelMessage,
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
    input_sample_rate: int
    input_frame_samples: int


class StateMessage(_Message):
    """See :class:`~jarvis_core.domain.events.StateChanged`."""

    type: Literal["state"] = "state"
    state: AssistantState


class WakeMessage(_Message):
    """See :class:`~jarvis_core.domain.events.WakeDetected`."""

    type: Literal["wake"] = "wake"


class TranscriptMessage(_Message):
    """See :class:`~jarvis_core.domain.events.TranscriptReady`."""

    type: Literal["transcript"] = "transcript"
    text: str


class AssistantDeltaMessage(_Message):
    """See :class:`~jarvis_core.domain.events.AssistantTextDelta`."""

    type: Literal["assistant_delta"] = "assistant_delta"
    text: str


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


class ErrorMessage(_Message):
    """See :class:`~jarvis_core.domain.events.ErrorOccurred`."""

    type: Literal["error"] = "error"
    message: str


ServerMessage = (
    ReadyMessage
    | StateMessage
    | WakeMessage
    | TranscriptMessage
    | AssistantDeltaMessage
    | SpeechSegmentMessage
    | TurnCompleteMessage
    | ErrorMessage
)


def to_server_message(event: VoiceEvent) -> ServerMessage:
    """Map a domain event to its JSON wire representation."""
    match event:
        case StateChanged(state=state):
            return StateMessage(state=state)
        case WakeDetected():
            return WakeMessage()
        case TranscriptReady(text=text):
            return TranscriptMessage(text=text)
        case AssistantTextDelta(text=text):
            return AssistantDeltaMessage(text=text)
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
        case ErrorOccurred(message=message):
            return ErrorMessage(message=message)
    raise TypeError(f"Unhandled event type: {type(event).__name__}")  # pragma: no cover
