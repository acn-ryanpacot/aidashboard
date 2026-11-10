"""The HTTP and WebSocket delivery layer, wired to fakes."""

from __future__ import annotations

import io
import json
import wave
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from jarvis_core.api.app import create_app
from jarvis_core.application.greeting import GreetingCache
from jarvis_core.application.persona import Persona
from jarvis_core.config import Settings
from jarvis_core.container import Container
from tests.fakes import FakeLlm, FakeStt, FakeTts, FakeVad, FakeWake


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(_env_file=None)
    tts = FakeTts()
    container = Container(
        settings=settings,
        persona=Persona("Jarvis", "Ryan", settings.greeting),
        llm=FakeLlm(["Good afternoon, Ryan. All systems are nominal."]),
        greeting=GreetingCache(settings.greeting, tts),
        stt=FakeStt(),
        tts=tts,
        wake_factory=FakeWake,
        vad_factory=FakeVad,
    )
    with TestClient(create_app(container=container)) as test_client:
        yield test_client


def receive_json(ws: WebSocketTestSession) -> dict[str, Any]:
    message: dict[str, Any] = json.loads(ws.receive_text())
    return message


def receive_until(ws: WebSocketTestSession, message_type: str) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    while True:
        message = receive_json(ws)
        seen.append(message)
        if message["type"] == "speech_segment":
            message["_wav"] = ws.receive_bytes()
        if message["type"] == message_type:
            return seen


def test_health_reports_capabilities(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["wake_word"] and body["speech_input"] and body["speech_output"]


def test_default_greeting_is_exact() -> None:
    assert Settings(_env_file=None).greeting == "How can I help you Ryan?"


def test_handshake_then_idle(client: TestClient) -> None:
    with client.websocket_connect("/ws/voice") as ws:
        ready = receive_json(ws)
        assert ready["type"] == "ready"
        assert ready["user_name"] == "Ryan"
        assert ready["input_sample_rate"] == 16_000
        assert receive_json(ws) == {"type": "state", "state": "idle"}


def test_activate_sends_greeting_header_then_wav(client: TestClient) -> None:
    with client.websocket_connect("/ws/voice") as ws:
        receive_until(ws, "state")
        ws.send_text(json.dumps({"type": "activate"}))
        messages = receive_until(ws, "speech_segment")
        segment = messages[-1]
        assert segment["kind"] == "greeting"
        assert segment["text"] == "How can I help you Ryan?"
        assert [w["word"] for w in segment["words"]][-1] == "Ryan?"
        with wave.open(io.BytesIO(segment["_wav"])) as wav:
            assert wav.getframerate() == FakeTts.SAMPLE_RATE

        ws.send_text(json.dumps({"type": "playback_ended", "segment_id": segment["segment_id"]}))
        assert receive_json(ws) == {"type": "state", "state": "listening"}


def test_text_query_round_trip(client: TestClient) -> None:
    with client.websocket_connect("/ws/voice") as ws:
        receive_until(ws, "state")
        ws.send_text(json.dumps({"type": "text_query", "text": "Status report"}))
        messages = receive_until(ws, "turn_complete")
        types = [m["type"] for m in messages]
        assert types[0:2] == ["state", "transcript"]
        assert "assistant_delta" in types
        assert "speech_segment" in types
        assert messages[-1]["text"] == "Good afternoon, Ryan. All systems are nominal."


def test_invalid_message_yields_error(client: TestClient) -> None:
    with client.websocket_connect("/ws/voice") as ws:
        receive_until(ws, "state")
        ws.send_text("{not json")
        assert receive_json(ws)["type"] == "error"


def test_foreign_origin_is_rejected(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/voice", headers={"origin": "https://evil.example"}) as ws,
    ):
        ws.receive_text()
