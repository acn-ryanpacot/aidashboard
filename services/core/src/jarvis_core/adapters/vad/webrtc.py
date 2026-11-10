"""Voice activity detection with Google's WebRTC VAD (tiny, fast, CPU-only)."""

from __future__ import annotations

from jarvis_core.domain.errors import ConfigurationError
from jarvis_core.domain.models import INPUT_SAMPLE_RATE, PCM16_SAMPLE_WIDTH


class WebRtcVoiceActivityDetector:
    """Implements :class:`~jarvis_core.domain.ports.VoiceActivityDetector`.

    WebRTC VAD only accepts 10/20/30 ms frames, so each 80 ms client frame is
    split into 20 ms sub-frames and classified by majority vote.

    Args:
        aggressiveness: ``0`` (permissive) … ``3`` (strict filtering of non-speech).
        sample_rate: Input sample rate (8, 16, 32 or 48 kHz).
        subframe_ms: Sub-frame length: 10, 20 or 30.
    """

    def __init__(
        self,
        *,
        aggressiveness: int = 2,
        sample_rate: int = INPUT_SAMPLE_RATE,
        subframe_ms: int = 20,
    ) -> None:
        try:
            import webrtcvad
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ConfigurationError(
                "webrtcvad-wheels is not installed. Run: uv sync --extra voice "
                "(or set JARVIS_VAD_ENGINE=energy)"
            ) from exc
        self._vad = webrtcvad.Vad(aggressiveness)
        self._sample_rate = sample_rate
        self._step = sample_rate * subframe_ms // 1000 * PCM16_SAMPLE_WIDTH

    def is_speech(self, frame: bytes) -> bool:
        """Return ``True`` if at least half of the sub-frames contain speech."""
        voiced = total = 0
        for start in range(0, len(frame) - self._step + 1, self._step):
            total += 1
            voiced += bool(
                self._vad.is_speech(frame[start : start + self._step], self._sample_rate)
            )
        return total > 0 and voiced * 2 >= total
