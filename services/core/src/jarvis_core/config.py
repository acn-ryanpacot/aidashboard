"""Typed application settings, loaded from environment variables and ``.env``.

Every setting can be overridden with an environment variable prefixed with
``JARVIS_`` — e.g. ``JARVIS_LLM_MODEL=qwen2.5:7b``. See ``.env.example`` and
``docs/configuration.md`` for the full reference.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from jarvis_core.application.persona import Formality, Humour, Verbosity
from jarvis_core.application.voice_session import BargeInMode

WakeEngine = Literal["openwakeword", "none"]
VadEngine = Literal["webrtc", "energy", "silero"]
SttEngine = Literal["faster_whisper", "none"]
TtsEngine = Literal["kokoro", "none"]

#: Origins allowed to open the voice WebSocket (Vite dev server + Tauri webview).
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
]


class McpServerSettings(BaseModel):
    """One stdio MCP server to launch (see ``docs/guides/mcp.md``)."""

    name: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,30}$")
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class Settings(BaseSettings):
    """All runtime configuration for the core service."""

    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Server -------------------------------------------------------------
    host: str = Field(default="127.0.0.1", description="Interface to bind. Keep it on loopback.")
    port: int = Field(default=8765, ge=1, le=65535)
    log_level: str = "INFO"
    log_json: bool = False
    allowed_origins: list[str] = Field(default_factory=lambda: list(DEFAULT_ALLOWED_ORIGINS))

    # --- Persona ------------------------------------------------------------
    user_name: str = "Ryan"
    assistant_name: str = "Jarvis"
    greeting_template: str = Field(
        default="How can I help you {user_name}?",
        description="Spoken verbatim after the wake word. `{user_name}` is substituted.",
    )
    persona_formality: Formality = "balanced"
    persona_verbosity: Verbosity = "balanced"
    persona_humour: Humour = "dry"

    # --- Wake word ----------------------------------------------------------
    wake_engine: WakeEngine = "openwakeword"
    wake_model: str = Field(
        default="hey_jarvis",
        description="Pretrained openWakeWord model name, or a path to a custom .onnx model.",
    )
    wake_threshold: float = Field(default=0.5, gt=0.0, lt=1.0)

    # --- Listening / endpointing ---------------------------------------------
    vad_engine: VadEngine = "webrtc"
    vad_aggressiveness: int = Field(default=2, ge=0, le=3)
    end_of_speech_ms: int = Field(
        default=800, ge=200, description="Trailing silence that ends a turn."
    )
    listen_timeout_ms: int = Field(
        default=6000, ge=1000, description="Give up if no speech starts."
    )
    follow_up_ms: int = Field(
        default=6000,
        ge=0,
        description="Keep listening after an answer (0 = require wake word again).",
    )
    max_utterance_ms: int = Field(default=15000, ge=2000)
    barge_in: BargeInMode = Field(
        default="wake_word", description="Interrupt Jarvis: wake_word, voice, or off."
    )
    barge_in_min_speech_ms: int = Field(default=400, ge=160)
    playback_grace_ms: int = Field(
        default=4000, ge=500, description="Assume a segment finished if not acknowledged."
    )

    # --- Voice ID -------------------------------------------------------------
    speaker_verification: bool = Field(
        default=False, description="Only answer the enrolled voice (needs the speaker extra)."
    )
    speaker_threshold: float = Field(default=0.30, ge=-1.0, le=1.0)
    speaker_enrollment_samples: int = Field(default=3, ge=1, le=10)

    # --- Speech-to-text -------------------------------------------------------
    stt_engine: SttEngine = "faster_whisper"
    stt_model: str = "base.en"
    stt_device: str = "auto"
    stt_compute_type: str = "int8"

    # --- Language model -------------------------------------------------------
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "llama3.2:3b"
    llm_temperature: float = Field(default=0.6, ge=0.0, le=2.0)
    llm_timeout_s: float = Field(default=120.0, gt=0)
    llm_think: bool | None = Field(
        default=None,
        description="Reasoning models only: false = skip thinking (faster), true = think.",
    )
    history_messages: int = Field(default=20, ge=0, description="Past messages kept as context.")

    # --- Brain: tools & memory -----------------------------------------------
    tools_enabled: bool = True
    max_tool_rounds: int = Field(default=4, ge=1, le=10)
    tool_routing: Literal["auto", "all"] = Field(
        default="auto",
        description="auto = attach only the tools a request needs (much faster on CPU).",
    )
    tool_routing_max_tools: int = Field(default=6, ge=1, le=50)
    memory_enabled: bool = True
    embedding_model: str = "nomic-embed-text"
    memory_min_score: float = Field(default=0.5, ge=0.0, le=1.0)
    memory_top_k: int = Field(default=3, ge=0, le=20)
    weather_enabled: bool = True
    default_location: str = Field(default="", description="Used when no place is named.")
    encyclopedia_enabled: bool = True
    encyclopedia_user_agent: str = Field(
        default="JarvisOS/0.2 (+https://localhost; self-hosted personal assistant) python-httpx",
        description="Wikimedia asks for a contact URL or email in the User-Agent.",
    )
    searxng_url: str = Field(default="", description="Self-hosted SearXNG for web search.")
    documents_dir: str = Field(default="", description="Folder of notes to search (RAG).")
    mcp_servers: list[McpServerSettings] = Field(default_factory=list)
    reminder_poll_s: float = Field(default=5.0, ge=1.0)

    # --- Dashboard data & briefing (defaults; editable in Settings) -----------
    news_feeds: list[str] = Field(
        default_factory=lambda: [
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://feeds.npr.org/1001/rss.xml",
        ]
    )
    calendar_urls: list[str] = Field(
        default_factory=list, description="Private ICS addresses or .ics file paths."
    )
    briefing_time: str = Field(default="", description="Daily spoken briefing, HH:MM (empty=off).")
    system_monitor_enabled: bool = True

    # --- Storage --------------------------------------------------------------
    data_dir: Path = Field(
        default_factory=lambda: Path.home() / ".jarvis-os",
        description="Database, voiceprint and model caches.",
    )

    # --- Text-to-speech -------------------------------------------------------
    tts_engine: TtsEngine = "kokoro"
    tts_lang_code: str = "b"
    tts_voice: str = "bm_george"
    tts_speed: float = Field(default=1.0, gt=0.25, le=2.0)

    @property
    def greeting(self) -> str:
        """The exact greeting spoken after the wake word."""
        return self.greeting_template.format(user_name=self.user_name)
