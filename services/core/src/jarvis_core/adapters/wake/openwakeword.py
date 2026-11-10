"""Always-on wake word with `openWakeWord <https://github.com/dscripka/openWakeWord>`_.

openWakeWord ships a pretrained ``hey_jarvis`` model. For the exact phrase
"Hello Jarvis", train a custom model for free with the project's Colab
notebook and point ``JARVIS_WAKE_MODEL`` at the resulting ``.onnx`` file —
see ``docs/guides/custom-wake-word.md``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from jarvis_core.domain.errors import ConfigurationError


def _import_openwakeword() -> None:
    try:
        import openwakeword  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ConfigurationError(
            "openwakeword is not installed. Run: uv sync --extra voice"
        ) from exc


def ensure_wake_models(model: str) -> None:
    """Download the shared feature models and, if needed, a pretrained wake model.

    Safe to call repeatedly; files already present are skipped.

    Args:
        model: Pretrained model name or a path to a custom model.
    """
    _import_openwakeword()
    from openwakeword.utils import download_models

    names = [] if Path(model).is_file() else [model]
    download_models(model_names=names)


class OpenWakeWordDetector:
    """Implements :class:`~jarvis_core.domain.ports.WakeWordDetector`.

    Args:
        model: Pretrained model name (``hey_jarvis``) or path to an ``.onnx`` file.
        threshold: Activation score in ``(0, 1)``; raise it to reduce false triggers.
    """

    def __init__(self, *, model: str = "hey_jarvis", threshold: float = 0.5) -> None:
        _import_openwakeword()
        from openwakeword.model import Model

        self._model = Model(wakeword_models=[model], inference_framework="onnx")
        self._threshold = threshold

    def process(self, frame: bytes) -> bool:
        """Score one 80 ms frame."""
        scores = self._model.predict(np.frombuffer(frame, dtype="<i2"))
        return any(float(score) >= self._threshold for score in scores.values())

    def reset(self) -> None:
        """Clear the rolling feature buffer."""
        self._model.reset()
