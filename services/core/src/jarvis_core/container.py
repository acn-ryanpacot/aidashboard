"""Composition root: the one place that knows which adapter implements which port.

Everything else depends on ports only. Wiring happens in two steps:

* :func:`build_container` creates the *real* adapters from :class:`Settings`
  (loading speech models, opening the database, …);
* :func:`assemble` wires adapters into the application services. Tests call
  it directly with fakes and an in-memory database.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from jarvis_core.adapters.persistence.database import Database
from jarvis_core.adapters.persistence.repositories import (
    SqliteMemoryStore,
    SqliteReminderRepository,
    SqliteTaskRepository,
)
from jarvis_core.application.brain import Brain
from jarvis_core.application.conversation import ConversationHistory
from jarvis_core.application.endpointing import EndpointingConfig, UtteranceRecorder
from jarvis_core.application.greeting import GreetingCache
from jarvis_core.application.hub import SessionHub
from jarvis_core.application.memory import MemoryService
from jarvis_core.application.persona import Persona, PersonaStyle
from jarvis_core.application.reminders import ReminderScheduler
from jarvis_core.application.speaker import SpeakerVerification
from jarvis_core.application.tools import builtin
from jarvis_core.application.tools.registry import ToolRegistry
from jarvis_core.application.voice_session import SessionConfig, VoiceSession
from jarvis_core.config import Settings
from jarvis_core.domain.models import INPUT_FRAME_SAMPLES, INPUT_SAMPLE_RATE
from jarvis_core.domain.ports import (
    DocumentSearch,
    EmbeddingModel,
    KnowledgeProvider,
    LanguageModel,
    ReminderRepository,
    SpeakerEncoder,
    SpeechToText,
    SupportsClose,
    SupportsWarmUp,
    TaskRepository,
    TextToSpeech,
    VoiceActivityDetector,
    VoiceEventSink,
    VoiceprintStore,
    WakeWordDetector,
    WeatherProvider,
    WebSearchProvider,
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
    brain: Brain
    tools: ToolRegistry
    greeting: GreetingCache
    hub: SessionHub
    tasks: TaskRepository
    reminders: ReminderRepository
    memory: MemoryService | None
    stt: SpeechToText | None
    tts: TextToSpeech | None
    wake_factory: Callable[[], WakeWordDetector] | None
    vad_factory: Callable[[], VoiceActivityDetector]
    speaker: SpeakerVerification | None = None
    database: Database | None = None
    scheduler: ReminderScheduler | None = None
    warmables: list[Any] = field(default_factory=list)
    closables: list[Any] = field(default_factory=list)
    tool_sources: list[Any] = field(default_factory=list)
    _tasks: list[asyncio.Task[Any]] = field(default_factory=list)

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
            brain=self.brain,
            greeting=self.greeting,
            recorder=recorder,
            history=ConversationHistory(s.history_messages),
            stt=self.stt,
            tts=self.tts,
            wake=self.wake_factory() if self.wake_factory else None,
            barge_vad=self.vad_factory() if s.barge_in == "voice" else None,
            speaker=self.speaker,
            config=SessionConfig(
                listen_timeout_ms=s.listen_timeout_ms,
                follow_up_ms=s.follow_up_ms,
                barge_in=s.barge_in,
                barge_in_min_speech_ms=s.barge_in_min_speech_ms,
                playback_grace_ms=s.playback_grace_ms,
                frame_ms=FRAME_MS,
            ),
        )

    async def warm_up(self) -> None:
        """Preload models, start MCP servers and background jobs."""
        for adapter in self.warmables:
            if isinstance(adapter, SupportsWarmUp):
                await adapter.warm_up()
        for source in self.tool_sources:
            try:
                self.tools.extend(await source.start())
            except Exception:
                log.warning("tool_source_failed", exc_info=True)
        if self.tts is not None:
            log.info("greeting_synthesizing", text=self.greeting.text)
            await self.greeting.get()
        if self.scheduler is not None:
            self._tasks.append(asyncio.create_task(self.scheduler.run(), name="jarvis-reminders"))
        log.info("brain_ready", tools=[spec.name for spec in self.tools.specs()])

    async def aclose(self) -> None:
        """Stop background jobs and release adapter resources."""
        for task in self._tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for adapter in reversed(self.closables):
            if isinstance(adapter, SupportsClose):
                with contextlib.suppress(Exception):
                    await adapter.aclose()
        if self.database is not None:
            self.database.close()


# ---------------------------------------------------------------- assembly


def assemble(
    settings: Settings,
    *,
    llm: LanguageModel,
    database: Database,
    vad_factory: Callable[[], VoiceActivityDetector],
    stt: SpeechToText | None = None,
    tts: TextToSpeech | None = None,
    wake_factory: Callable[[], WakeWordDetector] | None = None,
    embedder: EmbeddingModel | None = None,
    weather: WeatherProvider | None = None,
    knowledge: KnowledgeProvider | None = None,
    web_search: WebSearchProvider | None = None,
    documents: DocumentSearch | None = None,
    speaker_encoder: SpeakerEncoder | None = None,
    voiceprints: VoiceprintStore | None = None,
    tool_sources: Sequence[Any] = (),
    adapters: Sequence[Any] = (),
) -> Container:
    """Wire adapters into application services.

    Args:
        settings: Configuration.
        llm: Language model.
        database: Open database (``Database(":memory:")`` in tests).
        vad_factory: Creates a VAD per session.
        stt: Speech recognition.
        tts: Speech synthesis.
        wake_factory: Creates a wake-word detector per session.
        embedder: Embeddings for memory search.
        weather: Weather provider.
        knowledge: Encyclopedia provider.
        web_search: Web search provider.
        documents: Local document search.
        speaker_encoder: Voice-ID embedding model.
        voiceprints: Voice-ID persistence.
        tool_sources: Async tool providers started during warm-up (MCP).
        adapters: Extra objects to warm up / close with the container.
    """
    s = settings
    hub = SessionHub()
    persona = Persona(
        s.assistant_name,
        s.user_name,
        s.greeting,
        PersonaStyle(s.persona_formality, s.persona_verbosity, s.persona_humour),
    )
    tasks = SqliteTaskRepository(database)
    reminders = SqliteReminderRepository(database)
    memory = (
        MemoryService(
            SqliteMemoryStore(database),
            embedder,
            min_score=s.memory_min_score,
            top_k=s.memory_top_k,
        )
        if s.memory_enabled
        else None
    )

    tools = ToolRegistry()
    if s.tools_enabled:
        tools.extend(builtin.time_tools())
        tools.extend(builtin.task_tools(tasks, hub))
        tools.extend(builtin.reminder_tools(reminders, hub))
        if memory is not None:
            tools.extend(builtin.memory_tools(memory, hub))
        if weather is not None:
            tools.extend(builtin.weather_tools(weather, s.default_location))
        if knowledge is not None:
            tools.extend(builtin.knowledge_tools(knowledge))
        if web_search is not None:
            tools.extend(builtin.web_search_tools(web_search))
        if documents is not None:
            tools.extend(builtin.document_tools(documents))

    speaker = (
        SpeakerVerification(
            speaker_encoder,
            voiceprints,
            threshold=s.speaker_threshold,
            samples_required=s.speaker_enrollment_samples,
        )
        if speaker_encoder is not None and voiceprints is not None
        else None
    )
    all_adapters = [llm, embedder, weather, knowledge, web_search, documents, stt, tts, *adapters]
    present = [a for a in all_adapters if a is not None]
    return Container(
        settings=s,
        persona=persona,
        brain=Brain(
            llm,
            persona,
            tools if s.tools_enabled else None,
            memory,
            max_tool_rounds=s.max_tool_rounds,
        ),
        tools=tools,
        greeting=GreetingCache(s.greeting, tts),
        hub=hub,
        tasks=tasks,
        reminders=reminders,
        memory=memory,
        stt=stt,
        tts=tts,
        wake_factory=wake_factory,
        vad_factory=vad_factory,
        speaker=speaker,
        database=database,
        scheduler=ReminderScheduler(
            reminders, hub, user_name=s.user_name, poll_s=s.reminder_poll_s
        ),
        warmables=present,
        closables=[*present, *tool_sources],
        tool_sources=list(tool_sources),
    )


# ------------------------------------------------------------ real adapters


def build_container(settings: Settings) -> Container:
    """Instantiate real adapters according to ``settings`` and assemble them.

    This is blocking (it loads speech models) — use :func:`build_container_async`
    from async code.
    """
    s = settings
    s.data_dir.mkdir(parents=True, exist_ok=True)
    database = Database(s.data_dir / "jarvis.db")
    embedder = _build_embedder(s) if s.memory_enabled or s.documents_dir else None
    stt = _build_stt(s)
    speaker_encoder, voiceprints = _build_speaker(s)
    return assemble(
        s,
        llm=_build_llm(s),
        database=database,
        vad_factory=_build_vad_factory(s),
        stt=stt,
        tts=_build_tts(s),
        wake_factory=_build_wake_factory(s),
        embedder=embedder,
        weather=_build_weather(s),
        knowledge=_build_knowledge(s),
        web_search=_build_web_search(s),
        documents=_build_documents(s, database, embedder),
        speaker_encoder=speaker_encoder if stt is not None else None,
        voiceprints=voiceprints,
        tool_sources=_build_mcp(s),
    )


async def build_container_async(settings: Settings) -> Container:
    """Build the container in a worker thread, then warm it up."""
    container = await asyncio.to_thread(build_container, settings)
    await container.warm_up()
    return container


def _build_llm(s: Settings) -> LanguageModel:
    from jarvis_core.adapters.llm.ollama import OllamaLanguageModel

    return OllamaLanguageModel(
        base_url=s.llm_base_url,
        model=s.llm_model,
        temperature=s.llm_temperature,
        timeout_s=s.llm_timeout_s,
    )


def _build_embedder(s: Settings) -> EmbeddingModel:
    from jarvis_core.adapters.llm.ollama import OllamaEmbeddingModel

    return OllamaEmbeddingModel(base_url=s.llm_base_url, model=s.embedding_model)


def _build_stt(s: Settings) -> SpeechToText | None:
    if s.stt_engine == "none":
        return None
    from jarvis_core.adapters.stt.faster_whisper import FasterWhisperSpeechToText

    log.info("stt_loading", model=s.stt_model, device=s.stt_device)
    return FasterWhisperSpeechToText(
        model_size=s.stt_model, device=s.stt_device, compute_type=s.stt_compute_type
    )


def _build_tts(s: Settings) -> TextToSpeech | None:
    if s.tts_engine == "none":
        return None
    from jarvis_core.adapters.tts.kokoro import KokoroTextToSpeech

    log.info("tts_loading", voice=s.tts_voice)
    return KokoroTextToSpeech(lang_code=s.tts_lang_code, voice=s.tts_voice, speed=s.tts_speed)


def _build_wake_factory(s: Settings) -> Callable[[], WakeWordDetector] | None:
    if s.wake_engine == "none":
        return None
    from jarvis_core.adapters.wake.openwakeword import OpenWakeWordDetector, ensure_wake_models

    log.info("wake_model_loading", model=s.wake_model)
    ensure_wake_models(s.wake_model)

    def factory() -> WakeWordDetector:
        return OpenWakeWordDetector(model=s.wake_model, threshold=s.wake_threshold)

    return factory


def _build_vad_factory(s: Settings) -> Callable[[], VoiceActivityDetector]:
    if s.vad_engine == "energy":
        from jarvis_core.adapters.vad.energy import EnergyVoiceActivityDetector

        return EnergyVoiceActivityDetector
    if s.vad_engine == "silero":
        from jarvis_core.adapters.vad.silero import SileroVoiceActivityDetector

        SileroVoiceActivityDetector()  # fail fast if the dependency is missing
        return SileroVoiceActivityDetector

    from jarvis_core.adapters.vad.webrtc import WebRtcVoiceActivityDetector

    def factory() -> VoiceActivityDetector:
        return WebRtcVoiceActivityDetector(aggressiveness=s.vad_aggressiveness)

    return factory


def _build_speaker(s: Settings) -> tuple[SpeakerEncoder | None, VoiceprintStore | None]:
    from jarvis_core.adapters.persistence.voiceprint import FileVoiceprintStore

    if not s.speaker_verification:
        return None, None
    from jarvis_core.adapters.speaker.speechbrain import SpeechBrainSpeakerEncoder

    log.info("speaker_model_loading")
    encoder = SpeechBrainSpeakerEncoder(cache_dir=s.data_dir / "models" / "ecapa")
    return encoder, FileVoiceprintStore(s.data_dir / "voiceprint.json")


def _build_weather(s: Settings) -> WeatherProvider | None:
    if not (s.tools_enabled and s.weather_enabled):
        return None
    from jarvis_core.adapters.web.open_meteo import OpenMeteoWeatherProvider

    return OpenMeteoWeatherProvider()


def _build_knowledge(s: Settings) -> KnowledgeProvider | None:
    if not (s.tools_enabled and s.encyclopedia_enabled):
        return None
    from jarvis_core.adapters.web.wikipedia import WikipediaKnowledgeProvider

    return WikipediaKnowledgeProvider(user_agent=s.encyclopedia_user_agent)


def _build_web_search(s: Settings) -> WebSearchProvider | None:
    if not (s.tools_enabled and s.searxng_url):
        return None
    from jarvis_core.adapters.web.searxng import SearxngSearchProvider

    return SearxngSearchProvider(s.searxng_url)


def _build_documents(
    s: Settings, database: Database, embedder: EmbeddingModel | None
) -> DocumentSearch | None:
    if not (s.tools_enabled and s.documents_dir and embedder is not None):
        return None
    from jarvis_core.adapters.documents.folder_index import FolderDocumentIndex
    from jarvis_core.adapters.persistence.repositories import SqliteDocumentChunkStore

    return FolderDocumentIndex(
        Path(s.documents_dir).expanduser(), SqliteDocumentChunkStore(database), embedder
    )


def _build_mcp(s: Settings) -> list[Any]:
    if not (s.tools_enabled and s.mcp_servers):
        return []
    from jarvis_core.adapters.mcp.toolset import McpServer, McpToolset

    servers = [McpServer(m.name, m.command, tuple(m.args), dict(m.env)) for m in s.mcp_servers]
    return [McpToolset(servers)]
