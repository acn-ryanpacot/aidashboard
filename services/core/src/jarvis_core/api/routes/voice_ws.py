"""The ``/ws/voice`` endpoint: one WebSocket = one :class:`VoiceSession`."""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from jarvis_core.adapters.audio import encode_wav
from jarvis_core.api.protocol import (
    ActivateMessage,
    CancelMessage,
    ErrorMessage,
    PlaybackEndedMessage,
    ReadyMessage,
    ServerMessage,
    TextQueryMessage,
    client_message_adapter,
    to_server_message,
)
from jarvis_core.application.voice_session import VoiceSession
from jarvis_core.container import Container
from jarvis_core.domain.events import SpeechSegmentReady, VoiceEvent
from jarvis_core.domain.models import INPUT_FRAME_SAMPLES, INPUT_SAMPLE_RATE, PCM16_SAMPLE_WIDTH

log = structlog.get_logger(__name__)
router = APIRouter()

_FRAME_BYTES = INPUT_FRAME_SAMPLES * PCM16_SAMPLE_WIDTH


class WebSocketEventSink:
    """Adapter from :class:`~jarvis_core.domain.ports.VoiceEventSink` to a WebSocket.

    A lock guarantees a ``speech_segment`` header and its WAV payload are sent
    back-to-back even when several tasks publish concurrently.
    """

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self._lock = asyncio.Lock()

    async def publish(self, event: VoiceEvent) -> None:
        """Serialise and send ``event``."""
        async with self._lock:
            await self._send(to_server_message(event))
            if isinstance(event, SpeechSegmentReady):
                await self._ws.send_bytes(encode_wav(event.speech.audio))

    async def send(self, message: ServerMessage) -> None:
        """Send a protocol message that has no domain-event equivalent."""
        async with self._lock:
            await self._send(message)

    async def _send(self, message: ServerMessage) -> None:
        await self._ws.send_text(message.model_dump_json())


def _origin_allowed(websocket: WebSocket, allowed: list[str]) -> bool:
    """Browsers don't apply CORS to WebSockets, so check ``Origin`` ourselves.

    Requests without an Origin header (CLI tools, tests, native mobile apps)
    are allowed; the server only listens on loopback by default.
    """
    origin = websocket.headers.get("origin")
    return origin is None or origin in allowed


@router.websocket("/ws/voice")
async def voice_socket(websocket: WebSocket) -> None:
    """Run a voice session for the lifetime of the connection."""
    container: Container = websocket.app.state.container
    settings = container.settings
    if not _origin_allowed(websocket, settings.allowed_origins):
        log.warning("ws_origin_rejected", origin=websocket.headers.get("origin"))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    sink = WebSocketEventSink(websocket)
    session = container.new_session(sink)
    await sink.send(
        ReadyMessage(
            assistant_name=settings.assistant_name,
            user_name=settings.user_name,
            wake_word_enabled=container.wake_factory is not None,
            wake_model=settings.wake_model if container.wake_factory else None,
            speech_input_enabled=container.stt is not None,
            speech_output_enabled=container.tts is not None,
            input_sample_rate=INPUT_SAMPLE_RATE,
            input_frame_samples=INPUT_FRAME_SAMPLES,
        )
    )
    await session.start()
    log.info("ws_connected", client=str(websocket.client))

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if (data := message.get("bytes")) is not None:
                if len(data) == _FRAME_BYTES:
                    await session.handle_audio(data)
            elif (text := message.get("text")) is not None:
                await _dispatch(session, sink, text)
    except WebSocketDisconnect:
        pass
    finally:
        await session.close()
        log.info("ws_disconnected", client=str(websocket.client))


async def _dispatch(session: VoiceSession, sink: WebSocketEventSink, raw: str) -> None:
    """Route one JSON control message to the session."""
    try:
        command = client_message_adapter.validate_json(raw)
    except ValidationError:
        await sink.send(ErrorMessage(message="Unrecognised message."))
        return
    match command:
        case ActivateMessage():
            await session.activate()
        case TextQueryMessage(text=text):
            await session.handle_text_query(text)
        case PlaybackEndedMessage(segment_id=segment_id):
            await session.handle_playback_ended(segment_id)
        case CancelMessage():
            await session.cancel()
