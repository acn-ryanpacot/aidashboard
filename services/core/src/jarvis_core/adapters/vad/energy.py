"""Dependency-free voice activity detection based on signal energy."""

from __future__ import annotations

import numpy as np

from jarvis_core.adapters.audio import pcm16_to_float32


class EnergyVoiceActivityDetector:
    """Implements :class:`~jarvis_core.domain.ports.VoiceActivityDetector`.

    Classifies a frame as speech when its RMS level is well above a slowly
    adapting estimate of the room's noise floor. Less robust than WebRTC VAD
    in noisy rooms, but it needs nothing beyond NumPy.

    Args:
        ratio: How many times louder than the noise floor speech must be.
        min_rms: Absolute floor (full scale = 1.0) below which nothing is speech.
        adaptation: Noise-floor smoothing factor per non-speech frame (0…1).
    """

    def __init__(self, *, ratio: float = 3.0, min_rms: float = 0.01, adaptation: float = 0.05):
        self._ratio = ratio
        self._min_rms = min_rms
        self._adaptation = adaptation
        self._noise_floor = min_rms / ratio

    def is_speech(self, frame: bytes) -> bool:
        """Compare the frame's RMS energy to the adaptive threshold."""
        samples = pcm16_to_float32(frame)
        if samples.size == 0:
            return False
        rms = float(np.sqrt(np.mean(np.square(samples))))
        speech = rms >= max(self._min_rms, self._noise_floor * self._ratio)
        if not speech:
            self._noise_floor += self._adaptation * (rms - self._noise_floor)
        return speech
