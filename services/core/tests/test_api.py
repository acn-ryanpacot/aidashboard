"""The HTTP and WebSocket delivery layer, wired to fakes via :func:`assemble`."""

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

from jarvis_core.adapters.persistence.database import Database
from jarvis_core.api.app import create_app
from jarvis_core.config import Settings
from jarvis_core.container import Container, assemble
from jarvis_core.domain.models import ToolCall
from tests.fakes import (
    FakeEmbedder,
    FakeLlm,
    FakeSpeakerEncoder,
    FakeStt,
    FakeTts,
    FakeVad,
    FakeWake,
    FakeWeather,
    MemoryVoiceprintStore,
)


def make_container(llm: FakeLlm | None = None) -> Container:
    settings = Settings(_env_file=None, speaker_verification=True)
    return assemble(
        settings,
        llm=llm or FakeLlm(["Good afternoon, Ryan. All systems are nominal."]),
        database=Database(":memory:"),
        vad_factory=FakeVad,
        stt=FakeStt(),
        tts=FakeTts(),
        wake_factory=FakeWake,
        embedder=FakeEmbedder(),
        weather=FakeWeather(),
        speaker_encoder=FakeSpeakerEncoder(),
        voiceprints=MemoryVoiceprintStore(),
    )


@pytest.fixture
def container() -> Container:
    return make_container()


@pytest.fixture
def client(container: Container) -> Iterator[TestClient]:
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


# ------------------------------------------------------------------ HTTP


def test_health_reports_capabilities(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["version"] == "0.2.0"
    assert body["wake_word"] and body["speech_input"] and body["speech_output"]
    assert body["memory"] and body["speaker_verification"] and not body["speaker_enrolled"]
    assert {"get_current_time", "add_task", "set_reminder", "remember", "get_weather"} <= set(
        body["tools"]
    )


def test_default_greeting_is_exact() -> None:
    assert Settings(_env_file=None).greeting == "How can I help you Ryan?"


def test_tasks_rest_crud(client: TestClient) -> None:
    created = client.post("/api/tasks", json={"title": "Water the plants"})
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert [t["title"] for t in client.get("/api/tasks").json()] == ["Water the plants"]

    assert client.patch(f"/api/tasks/{task_id}", json={"done": True}).json()["done"] is True
    assert client.get("/api/tasks").json() == []
    assert len(client.get("/api/tasks", params={"include_done": True}).json()) == 1

    assert client.delete(f"/api/tasks/{task_id}").status_code == 204
    assert client.delete(f"/api/tasks/{task_id}").status_code == 404
    assert client.patch("/api/tasks/999", json={"done": True}).status_code == 404
    assert client.post("/api/tasks", json={"title": ""}).status_code == 422


def test_reminders_rest(client: TestClient) -> None:
    created = client.post(
        "/api/reminders", json={"text": "Dentist", "due_at": "2099-01-01T09:00:00+08:00"}
    )
    assert created.status_code == 201
    assert [r["text"] for r in client.get("/api/reminders").json()] == ["Dentist"]
    naive = client.post("/api/reminders", json={"text": "x", "due_at": "2099-01-01T09:00:00"})
    assert naive.status_code == 422
    assert client.delete(f"/api/reminders/{created.json()['id']}").status_code == 204


async def test_memories_rest(container: Container, client: TestClient) -> None:
    assert container.memory is not None
    record = await container.memory.remember("Ryan likes jazz")
    assert [m["text"] for m in client.get("/api/memories").json()] == ["Ryan likes jazz"]
    assert client.delete(f"/api/memories/{record.id}").status_code == 204
    assert client.delete(f"/api/memories/{record.id}").status_code == 404


def test_voiceprint_reset(client: TestClient) -> None:
    assert client.delete("/api/voiceprint").status_code == 204


# ------------------------------------------------------------- WebSocket


def test_handshake_then_idle(client: TestClient) -> None:
    with client.websocket_connect("/ws/voice") as ws:
        ready = receive_json(ws)
        assert ready["type"] == "ready" and ready["protocol_version"] == 2
        assert ready["user_name"] == "Ryan"
        assert ready["barge_in"] == "wake_word"
        assert ready["speaker_verification_enabled"] and not ready["speaker_enrolled"]
        assert "add_task" in ready["tools"]
        assert receive_json(ws) == {"type": "state", "state": "idle"}


def test_activate_sends_greeting_header_then_wav(client: TestClient) -> None:
    with client.websocket_connect("/ws/voice") as ws:
        receive_until(ws, "state")
        ws.send_text(json.dumps({"type": "activate"}))
        segment = receive_until(ws, "speech_segment")[-1]
        assert segment["kind"] == "greeting"
        assert segment["text"] == "How can I help you Ryan?"
        with wave.open(io.BytesIO(segment["_wav"])) as wav:
            assert wav.getframerate() == FakeTts.SAMPLE_RATE
        ws.send_text(json.dumps({"type": "playback_ended", "segment_id": segment["segment_id"]}))
        assert receive_json(ws) == {"type": "state", "state": "listening"}


def test_push_to_talk(client: TestClient) -> None:
    with client.websocket_connect("/ws/voice") as ws:
        receive_until(ws, "state")
        ws.send_text(json.dumps({"type": "listen"}))
        assert receive_json(ws) == {"type": "state", "state": "listening"}


def test_text_query_round_trip_with_metrics(client: TestClient) -> None:
    with client.websocket_connect("/ws/voice") as ws:
        receive_until(ws, "state")
        ws.send_text(json.dumps({"type": "text_query", "text": "Status report"}))
        messages = receive_until(ws, "metrics")
        types = [m["type"] for m in messages]
        assert types[0:2] == ["state", "transcript"]
        assert {"assistant_delta", "speech_segment", "turn_complete"} <= set(types)
        assert messages[-1]["stt_ms"] is None and messages[-1]["total_ms"] >= 0


def test_tool_call_over_websocket_updates_widgets() -> None:
    llm = FakeLlm(rounds=[[ToolCall("add_task", {"title": "Buy milk"})], ["Added, sir."]])
    with (
        TestClient(create_app(container=make_container(llm))) as client,
        client.websocket_connect("/ws/voice") as ws,
    ):
        receive_until(ws, "state")
        ws.send_text(json.dumps({"type": "text_query", "text": "add buy milk"}))
        messages = receive_until(ws, "metrics")
        by_type = {m["type"]: m for m in messages}
        assert by_type["tool"] == {
            "type": "tool",
            "name": "add_task",
            "label": "Updating your tasks",
        }
        assert by_type["data_changed"] == {"type": "data_changed", "topic": "tasks"}
        assert by_type["metrics"]["tools"] == ["add_task"]
        assert [t["title"] for t in client.get("/api/tasks").json()] == ["Buy milk"]


def test_rest_mutation_broadcasts_to_connected_clients(client: TestClient) -> None:
    with client.websocket_connect("/ws/voice") as ws:
        receive_until(ws, "state")
        client.post("/api/tasks", json={"title": "From the phone"})
        assert receive_json(ws) == {"type": "data_changed", "topic": "tasks"}


def test_enrollment_over_websocket(client: TestClient) -> None:
    with client.websocket_connect("/ws/voice") as ws:
        receive_until(ws, "state")
        ws.send_text(json.dumps({"type": "enroll_voice"}))
        assert receive_json(ws) == {
            "type": "enrollment",
            "status": "recording",
            "collected": 0,
            "required": 3,
        }
        ws.send_text(json.dumps({"type": "cancel"}))
        assert receive_until(ws, "enrollment")[-1]["status"] == "cancelled"


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
