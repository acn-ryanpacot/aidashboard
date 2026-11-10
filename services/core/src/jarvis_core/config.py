"""Typed application settings, loaded from environment variables and ``.env``.

Every setting can be overridden with an environment variable prefixed with
``JARVIS_`` — e.g. ``JARVIS_LLM_MODEL=qwen2.5:7b``. See ``.env.example`` and
``docs/configuration.md`` for the full reference.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

WakeEngine = Literal["openwakeword", "none"]
VadEngine = Literal["webrtc", "energy"]
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
    history_messages: int = Field(default=20, ge=0, description="Past messages kept as context.")

    # --- Text-to-speech -------------------------------------------------------
    tts_engine: TtsEngine = "kokoro"
    tts_lang_code: str = "b"
    tts_voice: str = "bm_george"
    tts_speed: float = Field(default=1.0, gt=0.25, le=2.0)

    @property
    def greeting(self) -> str:
        """The exact greeting spoken after the wake word."""
        return self.greeting_template.format(user_name=self.user_name)
