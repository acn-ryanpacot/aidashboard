"""Request authentication: this PC is trusted, other devices need a token.

Applied to every ``/api`` route. The voice WebSocket does the equivalent
check itself (see :mod:`jarvis_core.api.routes.voice_ws`), and the web UI's
static files are public because they contain no data.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from jarvis_core.application.devices import bearer_token, is_local
from jarvis_core.container import Container
from jarvis_core.domain.records import DeviceRecord


def request_is_local(request: Request) -> bool:
    """Whether the request comes straight from this PC (not via a proxy)."""
    client = request.client.host if request.client else None
    return is_local(client, request.headers)


async def require_access(request: Request) -> DeviceRecord | None:
    """Allow local requests; require a valid device token for everything else.

    Returns:
        The calling device, or ``None`` for this PC.

    Raises:
        HTTPException: 401 if a remote request has no valid token.
    """
    if request_is_local(request):
        return None
    container: Container = request.app.state.container
    device = await container.devices.verify(bearer_token(request.headers.get("authorization")))
    if device is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "This device isn't paired with Jarvis.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.state.device = device
    return device


async def require_local(request: Request) -> None:
    """Only this PC may call the route (e.g. pairing and revoking devices).

    Raises:
        HTTPException: 403 for any remote device, even a paired one.
    """
    if not request_is_local(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Manage devices from Jarvis on your PC.")
