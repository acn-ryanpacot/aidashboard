"""Pairing phones (and other devices) for remote access through Tailscale.

Everything under ``/api/devices`` is local-only: a paired phone can use
Jarvis but can't pair or revoke devices. ``/api/session`` tells any client
whether it is this PC or a paired device.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from jarvis_core.api.auth import request_is_local, require_local
from jarvis_core.container import Container
from jarvis_core.domain.records import DeviceRecord

router = APIRouter(prefix="/api/devices", tags=["devices"], dependencies=[Depends(require_local)])
session_router = APIRouter(prefix="/api", tags=["devices"])


def _container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


class DeviceOut(BaseModel):
    """A paired device (its token is never shown again)."""

    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None

    @classmethod
    def of(cls, device: DeviceRecord) -> DeviceOut:
        """Build from the domain record."""
        return cls(
            id=device.id,
            name=device.name,
            created_at=device.created_at,
            last_used_at=device.last_used_at,
        )


class DeviceIn(BaseModel):
    """Payload to pair a device."""

    name: str = Field(default="Phone", max_length=60)


class PairedDeviceOut(DeviceOut):
    """A newly paired device with its one-time token.

    ``pair_url`` opens Jarvis on the phone and stores the token; it's empty
    until ``tailscale serve`` publishes Jarvis (the token works either way).
    """

    token: str
    pair_url: str


class RemoteOut(BaseModel):
    """What the Phone access screen needs to show the next step."""

    installed: bool
    running: bool
    dns_name: str
    public_url: str
    port: int
    web_ui: bool


class SessionOut(BaseModel):
    """Who is calling: this PC (``local``) or a paired device."""

    local: bool
    device: str | None


@router.get("", response_model=list[DeviceOut])
async def list_devices(request: Request) -> list[DeviceOut]:
    """Paired devices, newest first."""
    return [DeviceOut.of(d) for d in await _container(request).devices.list_all()]


@router.post("", response_model=PairedDeviceOut, status_code=status.HTTP_201_CREATED)
async def pair_device(request: Request, body: DeviceIn) -> PairedDeviceOut:
    """Pair a device; the token in the response is shown only this once."""
    container = _container(request)
    device, token = await container.devices.create(body.name)
    remote = await container.remote.status() if container.remote else None
    base = remote.public_url if remote else ""
    return PairedDeviceOut(
        **DeviceOut.of(device).model_dump(),
        token=token,
        pair_url=f"{base}/#pair={token}" if base else "",
    )


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(request: Request, device_id: int) -> None:
    """Unpair a device; it's locked out immediately."""
    if not await _container(request).devices.revoke(device_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")


@router.get("/remote", response_model=RemoteOut)
async def remote_status(request: Request) -> RemoteOut:
    """Tailscale status and whether the web UI is built (for the setup steps)."""
    container = _container(request)
    remote = await container.remote.status() if container.remote else None
    return RemoteOut(
        installed=bool(remote and remote.installed),
        running=bool(remote and remote.running),
        dns_name=remote.dns_name if remote else "",
        public_url=remote.public_url if remote else "",
        port=container.settings.port,
        web_ui=bool(getattr(request.app.state, "web_ui", None)),
    )


@session_router.get("/session", response_model=SessionOut)
async def session_info(request: Request) -> SessionOut:
    """Whether the caller is this PC or a paired device (and which)."""
    device: DeviceRecord | None = getattr(request.state, "device", None)
    return SessionOut(local=request_is_local(request), device=device.name if device else None)
