"""Local speech recognition with `faster-whisper <https://github.com/SYSTRAN/faster-whisper>`_."""

from __future__ import annotations

from jarvis_core.adapters.audio import pcm16_to_float32
from jarvis_core.domain.errors import ConfigurationError, SpeechError
from jarvis_core.domain.models import INPUT_SAMPLE_RATE, AudioClip


class FasterWhisperSpeechToText:
    """Implements :class:`~jarvis_core.domain.ports.SpeechToText` using Whisper (CTranslate2).

    The model is downloaded from Hugging Face on first use and cached locally.

    Args:
        model_size: ``tiny.en``, ``base.en``, ``small.en``, ``medium.en``,
            ``large-v3`` … Larger is more accurate but slower.
        device: ``auto``, ``cpu`` or ``cuda``.
        compute_type: Quantisation, e.g. ``int8`` (fast on CPU) or ``float16`` (GPU).
        language: Spoken language code; fixing it skips language detection.
        beam_size: Beam search width.
    """

    def __init__(
        self,
        *,
        model_size: str = "base.en",
        device: str = "auto",
        compute_type: str = "int8",
        language: str = "en",
        beam_size: int = 5,
    ) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ConfigurationError(
                "faster-whisper is not installed. Run: uv sync --extra voice"
            ) from exc
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self._language = language
        self._beam_size = beam_size

    def transcribe(self, audio: AudioClip) -> str:
        """Transcribe a 16 kHz utterance."""
        if audio.sample_rate != INPUT_SAMPLE_RATE:
            raise SpeechError(f"Expected {INPUT_SAMPLE_RATE} Hz audio, got {audio.sample_rate} Hz")
        segments, _info = self._model.transcribe(
            pcm16_to_float32(audio.pcm16),
            language=self._language,
            beam_size=self._beam_size,
            vad_filter=True,  # suppresses Whisper's "hallucinations" on silence
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
