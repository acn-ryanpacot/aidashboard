"""Audio format helpers shared by adapters and the API layer."""

from __future__ import annotations

import io
import wave
from typing import Any

import numpy as np
import numpy.typing as npt

from jarvis_core.domain.models import PCM16_SAMPLE_WIDTH, AudioClip

FloatArray = npt.NDArray[np.float32]


def pcm16_to_float32(pcm16: bytes) -> FloatArray:
    """Convert 16-bit PCM bytes to float32 samples in ``[-1.0, 1.0]``."""
    samples = np.frombuffer(pcm16, dtype="<i2").astype(np.float32)
    result: FloatArray = samples / 32768.0
    return result


def float_to_pcm16(samples: npt.ArrayLike) -> bytes:
    """Convert float samples in ``[-1.0, 1.0]`` to 16-bit little-endian PCM bytes."""
    array: npt.NDArray[Any] = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    return (array * 32767.0).astype("<i2").tobytes()


def encode_wav(clip: AudioClip) -> bytes:
    """Wrap a PCM16 clip in a WAV container (browsers decode WAV natively)."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(PCM16_SAMPLE_WIDTH)
        wav.setframerate(clip.sample_rate)
        wav.writeframes(clip.pcm16)
    return buffer.getvalue()
