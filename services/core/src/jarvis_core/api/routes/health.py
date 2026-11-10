"""Liveness / capability endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from jarvis_core import __version__
from jarvis_core.container import Container

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Service status and which capabilities are active."""

    status: str
    version: str
    llm_model: str
    wake_word: bool
    speech_input: bool
    speech_output: bool
    barge_in: str
    speaker_verification: bool
    speaker_enrolled: bool
    memory: bool
    tools: list[str]
    clients: int


@router.get("/api/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Report that the service is up and what it can do."""
    container: Container = request.app.state.container
    speaker = container.speaker
    return HealthResponse(
        status="ok",
        version=__version__,
        llm_model=container.runtime.current.llm_model,
        wake_word=container.wake_factory is not None,
        speech_input=container.stt is not None,
        speech_output=container.tts is not None,
        barge_in=container.runtime.current.barge_in,
        speaker_verification=speaker is not None,
        speaker_enrolled=bool(speaker and speaker.enrolled),
        memory=container.memory is not None,
        tools=[spec.name for spec in container.tools.specs()],
        clients=len(container.hub),
    )
