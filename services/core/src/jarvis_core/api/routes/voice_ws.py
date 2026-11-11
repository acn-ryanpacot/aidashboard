"""The ``/ws/voice`` endpoint: one WebSocket = one :class:`VoiceSession`."""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from jarvis_core.adapters.audio import encode_wav
from jarvis_core.api.protocol import (
    ActivateMessage,
    BargeInMessage,
    CancelMessage,
    EnrollVoiceMessage,
    ErrorMessage,
    ListenMessage,
    PlaybackEndedMessage,
    ReadyMessage,
    ServerMessage,
    TextQueryMessage,
    client_message_adapter,
    to_server_message,
)
from jarvis_core.application.devices import (
    WS_PROTOCOL,
    is_local,
    offered_protocols,
    websocket_token,
)
from jarvis_core.application.voice_session import VoiceSession
from jarvis_core.container import Container
from jarvis_core.domain.events import SpeechSegmentReady, VoiceEvent
from jarvis_core.domain.models import INPUT_FRAME_SAMPLES, INPUT_SAMPLE_RATE, PCM16_SAMPLE_WIDTH

log = structlog.get_logger(__name__)
router = APIRouter()

_FRAME_BYTES = INPUT_FRAME_SAMPLES * PCM16_SAMPLE_WIDTH

#: Close code for a remote device without a valid token (the UI shows pairing).
UNPAIRED_CLOSE_CODE = 4401


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


def origin_allowed(origin: str | None, allowed: list[str], host: str | None = None) -> bool:
    """Browsers don't apply CORS to WebSockets, so check ``Origin`` ourselves.

    Allowed: no Origin header (CLI tools, tests, native mobile apps), a listed
    origin, or the page's own origin, i.e. the web UI served by this core
    (including through ``tailscale serve``, where ``host`` is the ts.net name).
    """
    if origin is None or origin in allowed:
        return True
    return host is not None and urlsplit(origin).netloc.lower() == host.lower()


def ready_message(container: Container) -> ReadyMessage:
    """Describe this server's capabilities to a new client."""
    s = container.settings
    r = container.runtime.current
    return ReadyMessage(
        assistant_name=s.assistant_name,
        user_name=r.user_name,
        wake_word_enabled=container.wake_factory is not None,
        wake_model=s.wake_model if container.wake_factory else None,
        speech_input_enabled=container.stt is not None,
        speech_output_enabled=container.tts is not None,
        barge_in=r.barge_in if container.stt is not None else "off",
        barge_in_min_speech_ms=r.barge_in_min_speech_ms,
        speaker_verification_enabled=container.speaker is not None,
        speaker_enrolled=bool(container.speaker and container.speaker.enrolled),
        tools=[spec.name for spec in container.tools.specs()],
        input_sample_rate=INPUT_SAMPLE_RATE,
        input_frame_samples=INPUT_FRAME_SAMPLES,
    )


@router.websocket("/ws/voice")
async def voice_socket(websocket: WebSocket) -> None:
    """Run a voice session for the lifetime of the connection."""
    container: Container = websocket.app.state.container
    headers = websocket.headers
    host = headers.get("x-forwarded-host") or headers.get("host")
    if not origin_allowed(headers.get("origin"), container.settings.allowed_origins, host):
        log.warning("ws_origin_rejected", origin=headers.get("origin"))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    protocols_header = headers.get("sec-websocket-protocol")
    client = websocket.client.host if websocket.client else None
    device = (
        None
        if is_local(client, headers)
        else await container.devices.verify(websocket_token(protocols_header))
    )

    # Echo our subprotocol only if the client offered it (browsers require that).
    subprotocol = WS_PROTOCOL if WS_PROTOCOL in offered_protocols(protocols_header) else None
    await websocket.accept(subprotocol=subprotocol)
    if device is None and not is_local(client, headers):
        # Closing after accept lets the browser see the code (before, it's a bare 403).
        log.warning("ws_device_rejected", client=client)
        await websocket.close(code=UNPAIRED_CLOSE_CODE, reason="unpaired")
        return
    if device is not None:
        log.info("ws_device", device=device.name)
    sink = WebSocketEventSink(websocket)
    session = container.new_session(sink)
    await sink.send(ready_message(container))
    await session.start()
    container.hub.register(session, sink)
    log.info("ws_connected", client=str(websocket.client), clients=len(container.hub))

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
        container.hub.unregister(session)
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
        case ListenMessage():
            await session.listen()
        case TextQueryMessage(text=text):
            await session.handle_text_query(text)
        case PlaybackEndedMessage(segment_id=segment_id):
            await session.handle_playback_ended(segment_id)
        case CancelMessage():
            await session.cancel()
        case BargeInMessage():
            await session.handle_barge_in()
        case EnrollVoiceMessage():
            await session.start_enrollment()
