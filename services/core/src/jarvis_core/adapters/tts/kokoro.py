"""Local neural speech with `Kokoro <https://huggingface.co/hexgrad/Kokoro-82M>`_ (Apache-2.0)."""

from __future__ import annotations

from typing import Any

import numpy as np

from jarvis_core.adapters.audio import float_to_pcm16
from jarvis_core.adapters.tts.timing import estimate_word_timings
from jarvis_core.domain.errors import ConfigurationError, SpeechError
from jarvis_core.domain.models import AudioClip, SynthesizedSpeech, WordTiming

KOKORO_SAMPLE_RATE = 24_000
KOKORO_REPO = "hexgrad/Kokoro-82M"


class KokoroTextToSpeech:
    """Implements :class:`~jarvis_core.domain.ports.TextToSpeech` with Kokoro-82M.

    Kokoro's English pipeline reports a start/end timestamp per token, which
    we pass through as :class:`WordTiming` so the UI can highlight each word
    as it is spoken. Weights (~330 MB) download from Hugging Face on first use.

    Args:
        lang_code: ``a`` = American English, ``b`` = British English.
        voice: Voice id, e.g. ``bm_george``, ``bm_lewis``, ``am_michael``.
        speed: Speaking rate multiplier.
        device: ``cpu``, ``cuda`` or ``None`` to auto-detect.
    """

    def __init__(
        self,
        *,
        lang_code: str = "b",
        voice: str = "bm_george",
        speed: float = 1.0,
        device: str | None = None,
    ) -> None:
        try:
            from kokoro import KPipeline
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ConfigurationError("kokoro is not installed. Run: uv sync --extra voice") from exc
        self._pipeline = KPipeline(lang_code=lang_code, repo_id=KOKORO_REPO, device=device)
        self._voice = voice
        self._speed = speed

    def synthesize(self, text: str) -> SynthesizedSpeech:
        """Render ``text`` (one sentence or a short paragraph) to speech."""
        chunks: list[np.ndarray[Any, Any]] = []
        words: list[WordTiming] = []
        offset = 0.0
        try:
            for result in self._pipeline(text, voice=self._voice, speed=self._speed):
                if result.audio is None:
                    continue
                samples = _to_numpy(result.audio)
                words.extend(_word_timings(result.tokens, offset))
                chunks.append(samples)
                offset += len(samples) / KOKORO_SAMPLE_RATE
        except Exception as exc:
            raise SpeechError(f"Speech synthesis failed: {exc}") from exc

        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        clip = AudioClip(float_to_pcm16(audio), KOKORO_SAMPLE_RATE)
        timings = tuple(words) or estimate_word_timings(text, clip.duration_seconds)
        return SynthesizedSpeech(text=text, audio=clip, words=timings)


def _to_numpy(audio: Any) -> np.ndarray[Any, Any]:
    """Kokoro returns a torch tensor; accept plain arrays too."""
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    return np.asarray(audio, dtype=np.float32).reshape(-1)


def _word_timings(tokens: Any, offset: float) -> list[WordTiming]:
    """Convert Kokoro tokens to word timings, skipping punctuation-only tokens."""
    timings: list[WordTiming] = []
    for token in tokens or ():
        start, end = getattr(token, "start_ts", None), getattr(token, "end_ts", None)
        word = getattr(token, "text", "")
        if start is None or end is None or not any(ch.isalnum() for ch in word):
            continue
        timings.append(WordTiming(word, round(offset + start, 3), round(offset + end, 3)))
    return timings
