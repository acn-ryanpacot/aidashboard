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
    SqliteDeviceTokenRepository,
    SqliteMemoryStore,
    SqlitePreferenceStore,
    SqliteReminderRepository,
    SqliteTaskRepository,
    SqliteTimerRepository,
)
from jarvis_core.application.brain import Brain
from jarvis_core.application.briefing import BriefingScheduler, BriefingService
from jarvis_core.application.conversation import ConversationHistory
from jarvis_core.application.devices import DeviceAccess
from jarvis_core.application.endpointing import EndpointingConfig, UtteranceRecorder
from jarvis_core.application.greeting import GreetingCache
from jarvis_core.application.hub import SessionHub
from jarvis_core.application.information import NewsService, ScheduleService, WeatherService
from jarvis_core.application.memory import MemoryService
from jarvis_core.application.persona import Persona, PersonaStyle
from jarvis_core.application.portfolio import PortfolioService
from jarvis_core.application.reminders import ReminderScheduler
from jarvis_core.application.runtime_settings import RuntimeSettings, SettingsService
from jarvis_core.application.speaker import SpeakerVerification
from jarvis_core.application.stock_alerts import StockAlertScheduler, StockAlertService
from jarvis_core.application.timers import TimerScheduler
from jarvis_core.application.tools import builtin
from jarvis_core.application.tools.registry import Tool, ToolRegistry
from jarvis_core.application.tools.routing import ToolRouter, mcp_group
from jarvis_core.application.voice_session import SessionConfig, VoiceSession
from jarvis_core.config import Settings
from jarvis_core.domain.models import INPUT_FRAME_SAMPLES, INPUT_SAMPLE_RATE
from jarvis_core.domain.ports import (
    CalendarProvider,
    DocumentSearch,
    EmbeddingModel,
    KnowledgeProvider,
    LanguageModel,
    NewsProvider,
    PortfolioSource,
    PreferenceStore,
    ReminderRepository,
    RemoteAccessProbe,
    SpeakerEncoder,
    SpeechToText,
    StockAlertSource,
    SupportsClose,
    SupportsFeedUrl,
    SupportsModelSwitch,
    SupportsVoiceConfig,
    SupportsWarmUp,
    SystemMonitor,
    TaskRepository,
    TextToSpeech,
    TimerRepository,
    VoiceActivityDetector,
    VoiceEventSink,
    VoiceprintStore,
    WakeWordDetector,
    WeatherProvider,
    WebSearchProvider,
)

log = structlog.get_logger(__name__)

FRAME_MS = INPUT_FRAME_SAMPLES * 1000 // INPUT_SAMPLE_RATE


def runtime_defaults(s: Settings) -> RuntimeSettings:
    """The environment's values for every setting editable in the dashboard."""
    return RuntimeSettings(
        user_name=s.user_name,
        persona_formality=s.persona_formality,
        persona_verbosity=s.persona_verbosity,
        persona_humour=s.persona_humour,
        tts_voice=s.tts_voice,
        tts_speed=s.tts_speed,
        wake_threshold=s.wake_threshold,
        end_of_speech_ms=s.end_of_speech_ms,
        listen_timeout_ms=s.listen_timeout_ms,
        follow_up_ms=s.follow_up_ms,
        barge_in=s.barge_in,
        barge_in_min_speech_ms=s.barge_in_min_speech_ms,
        speaker_threshold=s.speaker_threshold,
        llm_model=s.llm_model,
        default_location=s.default_location,
        briefing_time=s.briefing_time,
        news_feeds=list(s.news_feeds),
        calendar_urls=list(s.calendar_urls),
        portfolio_feed_url=s.portfolio_feed_url,
    )


@dataclass
class Container:
    """Long-lived services shared by all voice sessions.

    Stateless or thread-safe adapters (models) are singletons; stateful ones
    (wake word, VAD) are created per session through factories.
    """

    settings: Settings
    runtime: SettingsService
    preferences: PreferenceStore
    brain: Brain
    tools: ToolRegistry
    greeting: GreetingCache
    hub: SessionHub
    tasks: TaskRepository
    reminders: ReminderRepository
    timers: TimerRepository
    devices: DeviceAccess
    memory: MemoryService | None
    stt: SpeechToText | None
    tts: TextToSpeech | None
    llm: LanguageModel
    wake_factory: Callable[[], WakeWordDetector] | None
    vad_factory: Callable[[], VoiceActivityDetector]
    briefing: BriefingService
    weather: WeatherService | None = None
    news: NewsService | None = None
    schedule: ScheduleService | None = None
    portfolio: PortfolioService | None = None
    stock_alerts: StockAlertService | None = None
    remote: RemoteAccessProbe | None = None
    system: SystemMonitor | None = None
    speaker: SpeakerVerification | None = None
    router: ToolRouter | None = None
    database: Database | None = None
    background: list[Any] = field(default_factory=list)
    warmables: list[Any] = field(default_factory=list)
    closables: list[Any] = field(default_factory=list)
    tool_sources: list[Any] = field(default_factory=list)
    _tasks: list[asyncio.Task[Any]] = field(default_factory=list)

    @property
    def persona(self) -> Persona:
        """The persona in use (changes live with Settings)."""
        return self.brain.persona

    def session_config(self) -> tuple[SessionConfig, EndpointingConfig]:
        """Session and endpointing configuration from the current settings."""
        r = self.runtime.current
        return (
            SessionConfig(
                listen_timeout_ms=r.listen_timeout_ms,
                follow_up_ms=r.follow_up_ms,
                barge_in=r.barge_in,
                barge_in_min_speech_ms=r.barge_in_min_speech_ms,
                playback_grace_ms=self.settings.playback_grace_ms,
                frame_ms=FRAME_MS,
            ),
            EndpointingConfig(
                frame_ms=FRAME_MS,
                end_of_speech_ms=r.end_of_speech_ms,
                max_utterance_ms=self.settings.max_utterance_ms,
            ),
        )

    def new_session(self, sink: VoiceEventSink) -> VoiceSession:
        """Create a voice session bound to ``sink`` (one per client connection)."""
        config, endpointing = self.session_config()
        session = VoiceSession(
            sink=sink,
            brain=self.brain,
            greeting=self.greeting,
            recorder=UtteranceRecorder(self.vad_factory(), INPUT_SAMPLE_RATE, endpointing),
            history=ConversationHistory(self.settings.history_messages),
            stt=self.stt,
            tts=self.tts,
            wake=self.wake_factory() if self.wake_factory else None,
            speaker=self.speaker,
            config=config,
        )
        session.apply_config(config, wake_threshold=self.runtime.current.wake_threshold)
        return session

    async def warm_up(self) -> None:
        """Load stored settings, preload models, start MCP servers and background jobs."""
        await self.runtime.load()
        for adapter in self.warmables:
            if isinstance(adapter, SupportsWarmUp):
                await adapter.warm_up()
        for source in self.tool_sources:
            try:
                added: list[Tool] = await source.start()
            except Exception:
                log.warning("tool_source_failed", exc_info=True)
                continue
            self.tools.extend(added)
            if self.router is not None:
                for server in sorted({tool.name.split("__", 1)[0] for tool in added}):
                    specs = [t.spec for t in added if t.name.startswith(f"{server}__")]
                    self.router.add_group(mcp_group(server, specs))
        if self.tts is not None:
            log.info("greeting_synthesizing", text=self.greeting.text)
            await self.greeting.get()
        for job in self.background:
            self._tasks.append(asyncio.create_task(job.run(), name=type(job).__name__))
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
    news: NewsProvider | None = None,
    calendar: CalendarProvider | None = None,
    portfolio: PortfolioSource | None = None,
    stock_alerts: StockAlertSource | None = None,
    remote: RemoteAccessProbe | None = None,
    system: SystemMonitor | None = None,
    speaker_encoder: SpeakerEncoder | None = None,
    voiceprints: VoiceprintStore | None = None,
    tool_sources: Sequence[Any] = (),
    adapters: Sequence[Any] = (),
) -> Container:
    """Wire adapters into application services.

    Args:
        settings: Configuration (defaults for the live, user-editable settings).
        llm: Language model.
        database: Open database (``Database(":memory:")`` in tests).
        vad_factory: Creates a VAD per session.
        stt: Speech recognition.
        tts: Speech synthesis.
        wake_factory: Creates a wake-word detector per session.
        embedder: Embeddings for memory search and tool routing.
        weather: Weather provider.
        knowledge: Encyclopedia provider.
        web_search: Web search provider.
        documents: Local document search.
        news: RSS/Atom reader.
        calendar: ICS reader.
        portfolio: Stock portfolio from a companion app (PisoTiyempo).
        stock_alerts: The user's stock alert rules in that app.
        remote: Tailscale status, for pairing phones.
        system: Host monitor.
        speaker_encoder: Voice-ID embedding model.
        voiceprints: Voice-ID persistence.
        tool_sources: Async tool providers started during warm-up (MCP).
        adapters: Extra objects to warm up / close with the container.
    """
    s = settings
    hub = SessionHub()
    preferences = SqlitePreferenceStore(database)
    runtime = SettingsService(runtime_defaults(s), preferences)

    def make_persona(r: RuntimeSettings) -> Persona:
        return Persona(
            s.assistant_name,
            r.user_name,
            s.greeting_template.format(user_name=r.user_name),
            PersonaStyle(r.persona_formality, r.persona_verbosity, r.persona_humour),
        )

    persona = make_persona(runtime.current)
    tasks = SqliteTaskRepository(database)
    reminders = SqliteReminderRepository(database)
    timers = SqliteTimerRepository(database)
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
    weather_service = (
        WeatherService(weather, lambda: runtime.current.default_location) if weather else None
    )
    news_service = NewsService(news, lambda: runtime.current.news_feeds) if news else None
    schedule_service = (
        ScheduleService(calendar, lambda: runtime.current.calendar_urls) if calendar else None
    )
    if isinstance(portfolio, SupportsFeedUrl):
        portfolio.set_feed_url(runtime.current.portfolio_feed_url)
    portfolio_service = PortfolioService(portfolio) if portfolio is not None else None
    alert_service = (
        StockAlertService(stock_alerts, preferences) if stock_alerts is not None else None
    )
    briefing = BriefingService(
        tasks=tasks,
        reminders=reminders,
        weather=weather_service,
        schedule=schedule_service,
        news=news_service,
        portfolio=portfolio_service,
    )

    tools = ToolRegistry()
    if s.tools_enabled:
        tools.extend(builtin.time_tools())
        tools.extend(builtin.task_tools(tasks, hub))
        tools.extend(builtin.reminder_tools(reminders, hub))
        tools.extend(builtin.timer_tools(timers, hub))
        if memory is not None:
            tools.extend(builtin.memory_tools(memory, hub))
        if weather_service is not None:
            tools.extend(
                builtin.weather_tools(weather_service, lambda: runtime.current.default_location)
            )
        if knowledge is not None:
            tools.extend(builtin.knowledge_tools(knowledge))
        if web_search is not None:
            tools.extend(builtin.web_search_tools(web_search))
        if documents is not None:
            tools.extend(builtin.document_tools(documents))
        if news_service is not None:
            tools.extend(builtin.news_tools(news_service))
        if schedule_service is not None:
            tools.extend(builtin.schedule_tools(schedule_service))
        if portfolio_service is not None:
            tools.extend(builtin.portfolio_tools(portfolio_service))
        if alert_service is not None:
            tools.extend(builtin.stock_alert_tools(alert_service))
        tools.extend(builtin.briefing_tools(briefing))

    router = (
        ToolRouter(embedder=embedder, max_tools=s.tool_routing_max_tools)
        if s.tools_enabled and s.tool_routing == "auto"
        else None
    )
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
    brain = Brain(
        llm,
        persona,
        tools if s.tools_enabled else None,
        memory,
        router=router,
        max_tool_rounds=s.max_tool_rounds,
    )
    greeting = GreetingCache(persona.greeting, tts)
    reminder_scheduler = ReminderScheduler(
        reminders, hub, user_name=persona.user_name, poll_s=s.reminder_poll_s
    )
    timer_scheduler = TimerScheduler(
        timers, hub, user_name=persona.user_name, poll_s=s.timer_poll_s
    )
    alert_scheduler = (
        StockAlertScheduler(
            alert_service,
            hub,
            has_listeners=lambda: len(hub) > 0,
            user_name=persona.user_name,
            poll_s=s.portfolio_alerts_poll_s,
        )
        if alert_service is not None
        else None
    )
    briefing_scheduler = BriefingScheduler(
        compose=brain.compose,
        briefing=briefing,
        notifier=hub,
        store=preferences,
        briefing_time=lambda: runtime.current.briefing_time,
        has_listeners=lambda: len(hub) > 0,
    )
    present = [
        a
        for a in (
            llm,
            embedder,
            weather,
            knowledge,
            web_search,
            documents,
            news,
            calendar,
            portfolio,
            stock_alerts,
            stt,
            tts,
            *adapters,
        )
        if a is not None
    ]
    container = Container(
        settings=s,
        runtime=runtime,
        preferences=preferences,
        brain=brain,
        tools=tools,
        greeting=greeting,
        hub=hub,
        tasks=tasks,
        reminders=reminders,
        timers=timers,
        devices=DeviceAccess(SqliteDeviceTokenRepository(database)),
        memory=memory,
        stt=stt,
        tts=tts,
        llm=llm,
        wake_factory=wake_factory,
        vad_factory=vad_factory,
        briefing=briefing,
        weather=weather_service,
        news=news_service,
        schedule=schedule_service,
        portfolio=portfolio_service,
        stock_alerts=alert_service,
        remote=remote,
        system=system,
        speaker=speaker,
        router=router,
        database=database,
        background=[
            reminder_scheduler,
            timer_scheduler,
            briefing_scheduler,
            *([alert_scheduler] if alert_scheduler is not None else []),
        ],
        warmables=present,
        closables=[*present, *tool_sources],
        tool_sources=list(tool_sources),
    )

    async def apply_settings(new: RuntimeSettings, old: RuntimeSettings) -> None:
        """Push changed settings into every live component."""
        persona_fields = ("user_name", "persona_formality", "persona_verbosity", "persona_humour")
        if any(getattr(new, f) != getattr(old, f) for f in persona_fields):
            updated = make_persona(new)
            brain.set_persona(updated)
            greeting.set_text(updated.greeting)
            reminder_scheduler.user_name = new.user_name
            timer_scheduler.user_name = new.user_name
            if alert_scheduler is not None:
                alert_scheduler.user_name = new.user_name
        if (new.tts_voice, new.tts_speed) != (old.tts_voice, old.tts_speed) and isinstance(
            tts, SupportsVoiceConfig
        ):
            tts.configure(voice=new.tts_voice, speed=new.tts_speed)
            greeting.set_engine(tts)
        if new.llm_model != old.llm_model and isinstance(llm, SupportsModelSwitch):
            llm.set_model(new.llm_model)
        if speaker is not None:
            speaker.threshold = new.speaker_threshold
        if news_service is not None and new.news_feeds != old.news_feeds:
            news_service.invalidate()
        if schedule_service is not None and new.calendar_urls != old.calendar_urls:
            schedule_service.invalidate()
        if new.portfolio_feed_url != old.portfolio_feed_url:
            if isinstance(portfolio, SupportsFeedUrl):
                portfolio.set_feed_url(new.portfolio_feed_url)
            if portfolio_service is not None:
                portfolio_service.invalidate()
        config, endpointing = container.session_config()
        for session in hub.sessions():
            session.apply_config(config, endpointing=endpointing, wake_threshold=new.wake_threshold)
        if new != old:
            await hub.data_changed("settings")

    runtime.on_change(apply_settings)
    return container


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
        news=_build_news(),
        calendar=_build_calendar(),
        portfolio=_build_portfolio(s),
        stock_alerts=_build_stock_alerts(s),
        remote=_build_remote(s),
        system=_build_system(s),
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
        think=s.llm_think,
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
    if not s.weather_enabled:
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


def _build_news() -> NewsProvider:
    from jarvis_core.adapters.web.rss import RssNewsProvider

    return RssNewsProvider()


def _build_calendar() -> CalendarProvider:
    from jarvis_core.adapters.calendar.ics import IcsCalendarProvider

    return IcsCalendarProvider()


def _build_portfolio(s: Settings) -> PortfolioSource | None:
    if not s.portfolio_enabled:
        return None
    from jarvis_core.adapters.portfolio.pisotiyempo import PisoTiyempoPortfolio

    export_dir = Path(s.portfolio_export_dir).expanduser() if s.portfolio_export_dir else None
    return PisoTiyempoPortfolio(s.portfolio_feed_url, export_dir)


def _build_stock_alerts(s: Settings) -> StockAlertSource | None:
    if not (s.portfolio_enabled and s.portfolio_alerts_enabled):
        return None
    from jarvis_core.adapters.portfolio.pisotiyempo import PisoTiyempoAlerts

    database = Path(s.portfolio_database).expanduser() if s.portfolio_database else None
    return PisoTiyempoAlerts(database)


def _build_remote(s: Settings) -> RemoteAccessProbe:
    from jarvis_core.adapters.system.tailscale import TailscaleProbe

    return TailscaleProbe(s.port)


def _build_system(s: Settings) -> SystemMonitor | None:
    if not s.system_monitor_enabled:
        return None
    from jarvis_core.adapters.system.monitor import PsutilSystemMonitor

    return PsutilSystemMonitor()


def _build_mcp(s: Settings) -> list[Any]:
    if not (s.tools_enabled and s.mcp_servers):
        return []
    from jarvis_core.adapters.mcp.toolset import McpServer, McpToolset

    servers = [McpServer(m.name, m.command, tuple(m.args), dict(m.env)) for m in s.mcp_servers]
    return [McpToolset(servers)]
