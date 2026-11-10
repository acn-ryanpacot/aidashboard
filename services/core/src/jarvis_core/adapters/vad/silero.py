"""Neural voice activity detection with `Silero VAD <https://github.com/snakers4/silero-vad>`_.

More robust than WebRTC VAD against keyboard clicks, fans and TV noise, at
the cost of a PyTorch dependency (already present with the ``voice`` extra).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from jarvis_core.adapters.audio import FloatArray, pcm16_to_float32
from jarvis_core.domain.errors import ConfigurationError
from jarvis_core.domain.models import INPUT_SAMPLE_RATE

#: Silero v5 consumes exactly 512 samples per call at 16 kHz.
CHUNK_SAMPLES = 512


class SileroVoiceActivityDetector:
    """Implements :class:`~jarvis_core.domain.ports.VoiceActivityDetector`.

    Each 80 ms client frame (1280 samples) is fed to Silero in 512-sample
    chunks; leftover samples carry over to the next frame. A frame counts as
    speech if any chunk's probability reaches ``threshold``. The model is
    stateful, so use one instance per session.

    Args:
        threshold: Speech probability threshold (0 to 1).
    """

    def __init__(self, *, threshold: float = 0.5) -> None:
        try:
            import torch
            from silero_vad import load_silero_vad
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ConfigurationError(
                "silero-vad is not installed. Run: uv sync --extra voice"
            ) from exc
        self._torch: Any = torch
        self._model: Any = load_silero_vad(onnx=True)
        self._threshold = threshold
        self._carry: FloatArray = np.zeros(0, dtype=np.float32)

    def is_speech(self, frame: bytes) -> bool:
        """Classify one frame."""
        samples = np.concatenate([self._carry, pcm16_to_float32(frame)])
        full_chunks = len(samples) // CHUNK_SAMPLES
        best = 0.0
        for index in range(full_chunks):
            chunk = samples[index * CHUNK_SAMPLES : (index + 1) * CHUNK_SAMPLES]
            probability = self._model(self._torch.from_numpy(chunk), INPUT_SAMPLE_RATE).item()
            best = max(best, float(probability))
        self._carry = samples[full_chunks * CHUNK_SAMPLES :]
        return best >= self._threshold
