"""Phone access: device tokens, local vs remote requests, WebSocket auth, web UI."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from jarvis_core.adapters.persistence.database import Database
from jarvis_core.adapters.persistence.repositories import SqliteDeviceTokenRepository
from jarvis_core.adapters.system.tailscale import TailscaleProbe, parse_serve, parse_status
from jarvis_core.api.app import create_app
from jarvis_core.application.devices import (
    DeviceAccess,
    bearer_token,
    hash_token,
    is_local,
    websocket_token,
)
from jarvis_core.config import Settings
from jarvis_core.container import Container, assemble
from jarvis_core.domain.records import RemoteAccessStatus
from jarvis_core.tokens_cli import main as token_cli
from tests.fakes import LOCAL, FakeLlm, FakeVad

PHONE = ("100.101.1.2", 51000)  # a Tailscale address
TS_NET = "https://jarvis-pc.tail1234.ts.net"


class FakeRemote:
    def __init__(self, status: RemoteAccessStatus) -> None:
        self.value = status

    async def status(self) -> RemoteAccessStatus:
        return self.value


def make_container(remote: FakeRemote | None = None) -> Container:
    return assemble(
        Settings(_env_file=None),
        llm=FakeLlm(["Hello from Jarvis."]),
        database=Database(":memory:"),
        vad_factory=FakeVad,
        remote=remote
        or FakeRemote(RemoteAccessStatus(True, True, "jarvis-pc.tail1234.ts.net", TS_NET)),
    )


# ------------------------------------------------------------------- rules


def test_local_means_loopback_without_a_proxy() -> None:
    assert is_local("127.0.0.1", {})
    assert is_local("::1", {})
    assert not is_local("100.101.1.2", {})
    assert not is_local("testclient", {})
    # `tailscale serve` connects from loopback but adds forwarding headers.
    assert not is_local("127.0.0.1", {"x-forwarded-for": "100.101.1.2"})
    assert not is_local("127.0.0.1", {"tailscale-user-login": "ryan@example.com"})


def test_token_extraction() -> None:
    assert bearer_token("Bearer abc") == "abc"
    assert bearer_token("bearer  abc ") == "abc"
    assert bearer_token("Basic abc") is None
    assert bearer_token(None) is None
    assert websocket_token("jarvis.v3, bearer.tok-123") == "tok-123"
    assert websocket_token("jarvis.v3") is None
    assert websocket_token("bearer.") is None


async def test_tokens_are_stored_hashed_and_can_be_revoked() -> None:
    db = Database(":memory:")
    access = DeviceAccess(SqliteDeviceTokenRepository(db))
    device, token = await access.create("  Ryan's phone ")
    assert device.name == "Ryan's phone" and len(token) >= 40

    def stored(conn: sqlite3.Connection) -> list[str]:
        return [r[0] for r in conn.execute("SELECT token_hash FROM device_tokens")]

    assert await db.run(stored) == [hash_token(token)]  # never the token itself
    verified = await access.verify(token)
    assert verified is not None and verified.id == device.id
    assert (await access.list_all())[0].last_used_at is not None
    assert await access.verify("wrong") is None
    assert await access.verify(None) is None

    assert await access.revoke(device.id)
    assert await access.verify(token) is None


# -------------------------------------------------------------------- HTTP


@pytest.fixture
def container() -> Container:
    return make_container()


@pytest.fixture
def pc(container: Container) -> Iterator[TestClient]:
    with TestClient(create_app(container=container), client=LOCAL) as client:
        yield client


def phone(container: Container, token: str | None = None) -> TestClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return TestClient(create_app(container=container), client=PHONE, headers=headers)


def test_pairing_from_the_pc_and_using_jarvis_from_the_phone(
    container: Container, pc: TestClient
) -> None:
    paired = pc.post("/api/devices", json={"name": "Pixel"})
    assert paired.status_code == 201
    body = paired.json()
    assert body["name"] == "Pixel"
    assert body["pair_url"] == f"{TS_NET}/#pair={body['token']}"
    assert pc.get("/api/session").json() == {"local": True, "device": None}

    with phone(container) as stranger:
        refused = stranger.get("/api/tasks")
        assert refused.status_code == 401
        assert refused.headers["www-authenticate"] == "Bearer"
        assert stranger.get("/api/health").status_code == 401

    with phone(container, body["token"]) as paired_phone:
        assert paired_phone.get("/api/tasks").status_code == 200
        assert paired_phone.get("/api/session").json() == {"local": False, "device": "Pixel"}
        # A phone can use Jarvis but not manage devices, even with a token.
        assert paired_phone.get("/api/devices").status_code == 403
        assert paired_phone.post("/api/devices", json={"name": "x"}).status_code == 403

    listed = pc.get("/api/devices").json()
    assert [d["name"] for d in listed] == ["Pixel"] and listed[0]["last_used_at"]
    assert pc.delete(f"/api/devices/{body['id']}").status_code == 204
    assert pc.delete(f"/api/devices/{body['id']}").status_code == 404
    with phone(container, body["token"]) as revoked:
        assert revoked.get("/api/tasks").status_code == 401


def test_requests_relayed_by_tailscale_serve_need_a_token(
    container: Container, pc: TestClient
) -> None:
    relayed = pc.get("/api/tasks", headers={"X-Forwarded-For": "100.101.1.2"})
    assert relayed.status_code == 401
    token = pc.post("/api/devices", json={}).json()["token"]
    ok = pc.get(
        "/api/tasks",
        headers={"X-Forwarded-For": "100.101.1.2", "Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 200
    relayed_with_token = {"X-Forwarded-For": "100.101.1.2", "Authorization": f"Bearer {token}"}
    assert pc.get("/api/devices", headers=relayed_with_token).status_code == 403


def test_pair_url_is_empty_until_tailscale_serve_publishes_jarvis() -> None:
    container = make_container(FakeRemote(RemoteAccessStatus(installed=False)))
    with TestClient(create_app(container=container), client=LOCAL) as pc:
        body = pc.post("/api/devices", json={"name": "Phone"}).json()
        assert body["pair_url"] == "" and body["token"]
        remote = pc.get("/api/devices/remote").json()
        assert remote["installed"] is False and remote["port"] == 8765


# --------------------------------------------------------------- WebSocket


def test_remote_websocket_needs_a_token(container: Container, pc: TestClient) -> None:
    with (
        phone(container) as stranger,
        stranger.websocket_connect("/ws/voice", subprotocols=["jarvis.v3"]) as ws,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        ws.receive_json()
    assert closed.value.code == 4401

    token = pc.post("/api/devices", json={"name": "Pixel"}).json()["token"]
    with (
        phone(container) as paired_phone,
        paired_phone.websocket_connect(
            "/ws/voice", subprotocols=["jarvis.v3", f"bearer.{token}"]
        ) as ws,
    ):
        assert ws.accepted_subprotocol == "jarvis.v3"
        assert ws.receive_json()["type"] == "ready"


def test_websocket_allows_the_page_served_by_the_core(pc: TestClient) -> None:
    same_origin = {"Origin": "http://testserver", "Host": "testserver"}
    with pc.websocket_connect("/ws/voice", headers=same_origin) as ws:
        assert ws.receive_json()["type"] == "ready"
    evil = {"Origin": "https://evil.example"}
    with pytest.raises(WebSocketDisconnect), pc.websocket_connect("/ws/voice", headers=evil):
        pass


# ------------------------------------------------------------------ web UI


def test_web_ui_is_served_and_the_api_still_wins(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<title>Jarvis</title>", encoding="utf-8")
    settings = Settings(_env_file=None, web_dist=str(tmp_path))
    container = assemble(
        settings, llm=FakeLlm(["ok"]), database=Database(":memory:"), vad_factory=FakeVad
    )
    with TestClient(create_app(container=container), client=PHONE) as client:
        assert "Jarvis" in client.get("/").text  # public: it holds no data
        assert client.get("/api/tasks").status_code == 401


# --------------------------------------------------------------- Tailscale


def test_tailscale_status_parsing() -> None:
    status = {"BackendState": "Running", "Self": {"DNSName": "jarvis-pc.tail1234.ts.net."}}
    assert parse_status(status) == (True, "jarvis-pc.tail1234.ts.net")
    assert parse_status({"BackendState": "NeedsLogin"}) == (False, "")
    assert parse_status(None) == (False, "")

    serve = {
        "TCP": {"443": {"HTTPS": True}},
        "Web": {
            "jarvis-pc.tail1234.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8765"}}}
        },
    }
    assert parse_serve(serve, 8765) == TS_NET
    assert parse_serve(serve, 9000) == ""
    other_port = {
        "Web": {"pc.ts.net:8443": {"Handlers": {"/": {"Proxy": "http://localhost:8765/"}}}}
    }
    assert parse_serve(other_port, 8765) == "https://pc.ts.net:8443"
    assert parse_serve({}, 8765) == ""


async def test_tailscale_probe_without_the_cli() -> None:
    probe = TailscaleProbe(8765, cli=str(Path("definitely-missing-tailscale.exe")))
    status = await probe.status()
    assert status.installed and not status.running  # the CLI path was given but fails


# --------------------------------------------------------------------- CLI


def test_token_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    assert token_cli(["create", "Pixel"], settings) == 0
    created = capsys.readouterr().out
    assert "Paired #1 Pixel" in created
    assert token_cli(["list"], settings) == 0
    assert "#1   Pixel" in capsys.readouterr().out
    assert token_cli(["revoke", "1"], settings) == 0
    assert token_cli(["revoke", "1"], settings) == 1
    with closing(sqlite3.connect(tmp_path / "jarvis.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM device_tokens").fetchone() == (0,)
