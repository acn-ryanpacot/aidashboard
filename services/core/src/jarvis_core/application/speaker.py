"""Voice ID: only respond to the enrolled user's voice."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from jarvis_core.application.vectors import cosine_similarity, mean_vector
from jarvis_core.domain.models import AudioClip
from jarvis_core.domain.ports import SpeakerEncoder, VoiceprintStore


class SpeakerVerification:
    """Compares utterances to an enrolled voiceprint.

    Enrollment averages the embeddings of a few utterances into a single
    voiceprint. Verification is cosine similarity against it; until someone
    enrolls, every voice is accepted.

    Args:
        encoder: Speaker-embedding model (e.g. SpeechBrain ECAPA).
        store: Where the voiceprint is persisted.
        threshold: Minimum similarity to accept an utterance.
        samples_required: Utterances needed to enroll.
    """

    def __init__(
        self,
        encoder: SpeakerEncoder,
        store: VoiceprintStore,
        *,
        threshold: float = 0.3,
        samples_required: int = 3,
    ) -> None:
        self._encoder = encoder
        self._store = store
        self.threshold = threshold
        self.samples_required = samples_required
        self._voiceprint = store.load()

    @property
    def enrolled(self) -> bool:
        """Whether a voiceprint exists."""
        return self._voiceprint is not None

    async def embed(self, audio: AudioClip) -> list[float]:
        """Speaker embedding of ``audio`` (runs the model in a worker thread)."""
        return await asyncio.to_thread(self._encoder.embed, audio)

    async def verify(self, audio: AudioClip) -> tuple[bool, float]:
        """Return ``(accepted, similarity)`` for an utterance."""
        if self._voiceprint is None:
            return True, 1.0
        score = cosine_similarity(await self.embed(audio), self._voiceprint)
        return score >= self.threshold, score

    async def enroll(self, embeddings: Sequence[Sequence[float]]) -> None:
        """Store the averaged voiceprint of ``embeddings``."""
        voiceprint = mean_vector(embeddings)
        await asyncio.to_thread(self._store.save, voiceprint)
        self._voiceprint = voiceprint

    async def clear(self) -> None:
        """Remove the voiceprint (accept everyone again)."""
        await asyncio.to_thread(self._store.clear)
        self._voiceprint = None
