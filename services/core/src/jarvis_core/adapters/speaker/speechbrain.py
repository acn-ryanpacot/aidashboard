"""Speaker embeddings with SpeechBrain's ECAPA-TDNN model (Apache-2.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jarvis_core.adapters.audio import pcm16_to_float32
from jarvis_core.domain.errors import ConfigurationError, SpeechError
from jarvis_core.domain.models import INPUT_SAMPLE_RATE, AudioClip

ECAPA_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"


class SpeechBrainSpeakerEncoder:
    """Implements :class:`~jarvis_core.domain.ports.SpeakerEncoder`.

    Produces 192-dimensional voice embeddings. Weights (~80 MB) download from
    Hugging Face on first use.

    Args:
        cache_dir: Where to keep the model files.
        source: Hugging Face model id.
    """

    def __init__(self, *, cache_dir: Path, source: str = ECAPA_SOURCE) -> None:
        try:
            import torch
            from speechbrain.inference.speaker import EncoderClassifier
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ConfigurationError(
                "speechbrain is not installed. Run: uv sync --extra voice --extra speaker"
            ) from exc
        self._torch: Any = torch
        options: dict[str, Any] = {"source": source, "savedir": str(cache_dir)}
        try:
            # Windows can't always create symlinks; copy the files instead.
            from speechbrain.utils.fetching import LocalStrategy

            options["local_strategy"] = LocalStrategy.COPY
        except ImportError:  # pragma: no cover - older SpeechBrain
            pass
        self._model: Any = EncoderClassifier.from_hparams(**options)

    def embed(self, audio: AudioClip) -> list[float]:
        """Embedding of a 16 kHz utterance."""
        if audio.sample_rate != INPUT_SAMPLE_RATE:
            raise SpeechError(f"Expected {INPUT_SAMPLE_RATE} Hz audio, got {audio.sample_rate} Hz")
        samples = self._torch.from_numpy(pcm16_to_float32(audio.pcm16)).unsqueeze(0)
        with self._torch.no_grad():
            embedding = self._model.encode_batch(samples)
        return [float(x) for x in embedding.squeeze().cpu().numpy()]
