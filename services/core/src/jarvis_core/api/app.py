"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jarvis_core import __version__
from jarvis_core.api.routes import dashboard, data, health, voice_ws
from jarvis_core.config import Settings
from jarvis_core.container import Container, build_container_async

log = structlog.get_logger(__name__)


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
    app.include_router(health.router)
    app.include_router(data.router)
    app.include_router(dashboard.router)
    app.include_router(voice_ws.router)
    return app
