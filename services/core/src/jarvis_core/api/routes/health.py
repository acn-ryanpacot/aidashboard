"""Liveness / capability endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from jarvis_core import __version__
from jarvis_core.container import Container

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Service status and which voice capabilities are active."""

    status: str
    version: str
    llm_model: str
    wake_word: bool
    speech_input: bool
    speech_output: bool


@router.get("/api/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Report that the service is up and what it can do."""
    container: Container = request.app.state.container
    return HealthResponse(
        status="ok",
        version=__version__,
        llm_model=container.settings.llm_model,
        wake_word=container.wake_factory is not None,
        speech_input=container.stt is not None,
        speech_output=container.tts is not None,
    )
