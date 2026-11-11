"""Who may use Jarvis: this PC freely, other devices only with a token.

Phone access goes through ``tailscale serve``, a reverse proxy that runs on
this PC and forwards to ``127.0.0.1``. So "the connection comes from
loopback" isn't enough to trust a request: proxied requests carry forwarding
headers, and those (or any non-loopback client) must present a device token.
See ``docs/adr/0016-phone-access.md``.

Tokens are 256-bit random strings shown once at pairing. Only their SHA-256
hash is stored, so a copy of the database can't be used to impersonate a
phone, and revoking a device is deleting its row.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from jarvis_core.domain.ports import DeviceTokenRepository
from jarvis_core.domain.records import DeviceRecord

#: Requests from these addresses come from this machine.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

#: Headers that mean a reverse proxy (e.g. ``tailscale serve``) relayed the request.
PROXY_HEADERS = ("x-forwarded-for", "forwarded", "x-forwarded-host", "tailscale-user-login")

#: WebSocket subprotocol spoken by Jarvis clients, and the prefix of the token one.
WS_PROTOCOL = "jarvis.v3"
WS_TOKEN_PREFIX = "bearer."

#: ``last_used_at`` is written at most this often per device.
TOUCH_INTERVAL = timedelta(minutes=1)

Clock = Callable[[], datetime]


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a token (what the database stores)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_local(client_host: str | None, headers: Mapping[str, str]) -> bool:
    """Whether a request comes straight from this PC (not via a proxy).

    Args:
        client_host: The peer address seen by the server.
        headers: Request headers (case-insensitive mapping or lower-cased keys).
    """
    if client_host not in LOOPBACK_HOSTS:
        return False
    return not any(headers.get(name) for name in PROXY_HEADERS)


def bearer_token(authorization: str | None) -> str | None:
    """The token from an ``Authorization: Bearer …`` header."""
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    return value.strip() or None if scheme.lower() == "bearer" else None


def websocket_token(protocols_header: str | None) -> str | None:
    """The token offered as a ``bearer.<token>`` WebSocket subprotocol.

    Browsers can't set headers on a WebSocket, and a ``?token=`` query would
    end up in access logs, so the token travels as a subprotocol instead.
    """
    for protocol in (p.strip() for p in (protocols_header or "").split(",")):
        if protocol.startswith(WS_TOKEN_PREFIX) and len(protocol) > len(WS_TOKEN_PREFIX):
            return protocol[len(WS_TOKEN_PREFIX) :]
    return None


def offered_protocols(protocols_header: str | None) -> list[str]:
    """The subprotocols a WebSocket client offered."""
    return [p.strip() for p in (protocols_header or "").split(",") if p.strip()]


class DeviceAccess:
    """Pairs, verifies and revokes remote devices.

    Args:
        repo: Device storage.
        clock: Current time (UTC).
    """

    def __init__(
        self, repo: DeviceTokenRepository, *, clock: Clock = lambda: datetime.now(UTC)
    ) -> None:
        self._repo = repo
        self._clock = clock

    async def create(self, name: str) -> tuple[DeviceRecord, str]:
        """Pair a new device; returns it and its token (shown only this once)."""
        token = secrets.token_urlsafe(32)
        record = await self._repo.add(name.strip() or "Phone", hash_token(token))
        return record, token

    async def verify(self, token: str | None) -> DeviceRecord | None:
        """The device a token belongs to, or ``None`` if it isn't valid."""
        if not token:
            return None
        record = await self._repo.find(hash_token(token))
        if record is None:
            return None
        now = self._clock()
        if record.last_used_at is None or now - record.last_used_at >= TOUCH_INTERVAL:
            await self._repo.touch(record.id, now)
        return record

    async def list_all(self) -> list[DeviceRecord]:
        """Every paired device, newest first."""
        return await self._repo.list_all()

    async def revoke(self, device_id: int) -> bool:
        """Unpair a device; its token stops working immediately."""
        return await self._repo.delete(device_id)
