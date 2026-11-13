"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import jarvis_core
from jarvis_core import __version__
from jarvis_core.api.auth import require_access
from jarvis_core.api.routes import (
    apps,
    dashboard,
    data,
    devices,
    health,
    knowledge,
    voice_ws,
)
from jarvis_core.config import Settings
from jarvis_core.container import Container, build_container_async

log = structlog.get_logger(__name__)


def web_ui_folder(settings: Settings) -> Path | None:
    """The built dashboard (``apps/desktop/dist``) to serve, if there is one.

    ``JARVIS_WEB_DIST`` wins; otherwise the folder next to this checkout is
    used once ``pnpm --filter @jarvis/desktop build`` has created it.
    """
    if settings.web_dist:
        folder = Path(settings.web_dist).expanduser()
    else:
        # services/core/src/jarvis_core/__init__.py → the repository root.
        parents = Path(jarvis_core.__file__).resolve().parents
        if len(parents) < 5:
            return None
        folder = parents[4] / "apps" / "desktop" / "dist"
    return folder if (folder / "index.html").is_file() else None


def create_app(settings: Settings | None = None, *, container: Container | None = None) -> FastAPI:
    """Create the API application.

    Args:
        settings: Configuration; loaded from the environment if omitted.
        container: A pre-built container (tests inject one wired with fakes).
            When omitted, adapters are built and warmed up during startup.

    Returns:
        A ready-to-serve FastAPI app.
    """
    settings = settings or (container.settings if container else Settings())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned = container is None
        active = container or await build_container_async(settings)
        app.state.container = active
        log.info("jarvis_online", host=settings.host, port=settings.port, llm=settings.llm_model)
        try:
            yield
        finally:
            if owned:
                await active.aclose()

    app = FastAPI(
        title="Jarvis OS Core",
        version=__version__,
        summary="Voice pipeline, AI brain and widget host for Jarvis OS.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    # This PC is trusted; any other device (e.g. a phone through `tailscale
    # serve`) needs a paired token. The WebSocket checks it itself.
    guarded = [Depends(require_access)]
    for router in (
        health.router,
        data.router,
        dashboard.router,
        apps.router,
        knowledge.router,
        devices.session_router,
        devices.router,
    ):
        app.include_router(router, dependencies=guarded)
    app.include_router(voice_ws.router)

    # The dashboard itself, for phones (mounted last so /api and /ws win).
    folder = web_ui_folder(settings)
    app.state.web_ui = folder
    if folder is not None:
        app.mount("/", StaticFiles(directory=folder, html=True), name="web-ui")
        log.info("web_ui_served", folder=str(folder))
    return app
