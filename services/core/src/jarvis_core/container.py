"""Composition root: the one place that knows which adapter implements which port.

Everything else depends on ports only. To swap an implementation (another
LLM, another voice), change the matching ``_build_*`` function below.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

import structlog

from jarvis_core.application.conversation import ConversationHistory
from jarvis_core.application.endpointing import EndpointingConfig, UtteranceRecorder
from jarvis_core.application.greeting import GreetingCache
from jarvis_core.application.persona import Persona
from jarvis_core.application.voice_session import SessionConfig, VoiceSession
from jarvis_core.config import Settings
from jarvis_core.domain.models import INPUT_FRAME_SAMPLES, INPUT_SAMPLE_RATE
from jarvis_core.domain.ports import (
    LanguageModel,
    SpeechToText,
    SupportsClose,
    SupportsWarmUp,
    TextToSpeech,
    VoiceActivityDetector,
    VoiceEventSink,
    WakeWordDetector,
)

log = structlog.get_logger(__name__)

FRAME_MS = INPUT_FRAME_SAMPLES * 1000 // INPUT_SAMPLE_RATE


@dataclass
class Container:
    """Long-lived services shared by all voice sessions.

    Stateless or thread-safe adapters (models) are singletons; stateful ones
    (wake word, VAD) are created per session through factories.
    """

    settings: Settings
    persona: Persona
    llm: LanguageModel
    greeting: GreetingCache
    stt: SpeechToText | None
    tts: TextToSpeech | None
    wake_factory: Callable[[], WakeWordDetector] | None
    vad_factory: Callable[[], VoiceActivityDetector]

    def new_session(self, sink: VoiceEventSink) -> VoiceSession:
        """Create a voice session bound to ``sink`` (one per client connection)."""
        s = self.settings
        recorder = UtteranceRecorder(
            self.vad_factory(),
            INPUT_SAMPLE_RATE,
            EndpointingConfig(
                frame_ms=FRAME_MS,
                end_of_speech_ms=s.end_of_speech_ms,
                max_utterance_ms=s.max_utterance_ms,
            ),
        )
        return VoiceSession(
            sink=sink,
            persona=self.persona,
            greeting=self.greeting,
            llm=self.llm,
            recorder=recorder,
            history=ConversationHistory(s.history_messages),
            stt=self.stt,
            tts=self.tts,
            wake=self.wake_factory() if self.wake_factory else None,
            config=SessionConfig(
                listen_timeout_ms=s.listen_timeout_ms, follow_up_ms=s.follow_up_ms
            ),
        )

    async def warm_up(self) -> None:
        """Preload models and the greeting so the first interaction is instant."""
        if isinstance(self.llm, SupportsWarmUp):
            await self.llm.warm_up()
        if self.tts is not None:
            log.info("greeting_synthesizing", text=self.greeting.text)
            await self.greeting.get()

    async def aclose(self) -> None:
        """Release adapter resources on shutdown."""
        for adapter in (self.llm, self.stt, self.tts):
            if isinstance(adapter, SupportsClose):
                await adapter.aclose()


def build_container(settings: Settings) -> Container:
    """Instantiate adapters according to ``settings``.

    This is blocking (it loads speech models) — call it via
    :func:`asyncio.to_thread` from async code, or use :func:`build_container_async`.
    """
    stt = _build_stt(settings)
    tts = _build_tts(settings)
    return Container(
        settings=settings,
        persona=Persona(settings.assistant_name, settings.user_name, settings.greeting),
        llm=_build_llm(settings),
        greeting=GreetingCache(settings.greeting, tts),
        stt=stt,
        tts=tts,
        wake_factory=_build_wake_factory(settings),
        vad_factory=_build_vad_factory(settings),
    )


async def build_container_async(settings: Settings) -> Container:
    """Build the container in a worker thread, then warm it up."""
    container = await asyncio.to_thread(build_container, settings)
    await container.warm_up()
    return container


# ------------------------------------------------------------------ builders


def _build_llm(settings: Settings) -> LanguageModel:
    from jarvis_core.adapters.llm.ollama import OllamaLanguageModel

    return OllamaLanguageModel(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        timeout_s=settings.llm_timeout_s,
    )


def _build_stt(settings: Settings) -> SpeechToText | None:
    if settings.stt_engine == "none":
        return None
    from jarvis_core.adapters.stt.faster_whisper import FasterWhisperSpeechToText

    log.info("stt_loading", model=settings.stt_model, device=settings.stt_device)
    return FasterWhisperSpeechToText(
        model_size=settings.stt_model,
        device=settings.stt_device,
        compute_type=settings.stt_compute_type,
    )


def _build_tts(settings: Settings) -> TextToSpeech | None:
    if settings.tts_engine == "none":
        return None
    from jarvis_core.adapters.tts.kokoro import KokoroTextToSpeech

    log.info("tts_loading", voice=settings.tts_voice)
    return KokoroTextToSpeech(
        lang_code=settings.tts_lang_code, voice=settings.tts_voice, speed=settings.tts_speed
    )


def _build_wake_factory(settings: Settings) -> Callable[[], WakeWordDetector] | None:
    if settings.wake_engine == "none":
        return None
    from jarvis_core.adapters.wake.openwakeword import OpenWakeWordDetector, ensure_wake_models

    log.info("wake_model_loading", model=settings.wake_model)
    ensure_wake_models(settings.wake_model)

    def factory() -> WakeWordDetector:
        return OpenWakeWordDetector(model=settings.wake_model, threshold=settings.wake_threshold)

    return factory


def _build_vad_factory(settings: Settings) -> Callable[[], VoiceActivityDetector]:
    if settings.vad_engine == "energy":
        from jarvis_core.adapters.vad.energy import EnergyVoiceActivityDetector

        return EnergyVoiceActivityDetector

    from jarvis_core.adapters.vad.webrtc import WebRtcVoiceActivityDetector

    def factory() -> VoiceActivityDetector:
        return WebRtcVoiceActivityDetector(aggressiveness=settings.vad_aggressiveness)

    return factory
