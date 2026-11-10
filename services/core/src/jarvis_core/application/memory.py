"""Long-term memory: facts Jarvis keeps across sessions."""

from __future__ import annotations

import structlog

from jarvis_core.application.vectors import cosine_similarity, keyword_overlap
from jarvis_core.domain.ports import EmbeddingModel, MemoryStore
from jarvis_core.domain.records import MemoryRecord, ScoredMemory

log = structlog.get_logger(__name__)


class MemoryService:
    """Stores facts and retrieves the ones relevant to a question.

    Retrieval is semantic when an embedding model is available (Ollama
    ``nomic-embed-text`` by default) and falls back to keyword overlap
    otherwise, so memory keeps working if the embedding model isn't pulled.

    Args:
        store: Persistence for memories.
        embedder: Optional embedding model.
        min_score: Minimum cosine similarity for a semantic match.
        top_k: How many memories :meth:`relevant` returns.
    """

    def __init__(
        self,
        store: MemoryStore,
        embedder: EmbeddingModel | None = None,
        *,
        min_score: float = 0.5,
        top_k: int = 3,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._min_score = min_score
        self._top_k = top_k
        self._embedder_failed = False

    async def remember(self, text: str) -> MemoryRecord:
        """Store ``text`` as a memory."""
        return await self._store.add(text, await self._embed(text))

    async def recall(self, query: str, limit: int | None = None) -> list[ScoredMemory]:
        """Memories most relevant to ``query``, best first."""
        limit = limit or self._top_k
        memories = await self._store.all()
        if not memories:
            return []
        query_vector = await self._embed(query)
        scored: list[ScoredMemory] = []
        for memory in memories:
            if query_vector is not None and memory.embedding is not None:
                score = cosine_similarity(query_vector, memory.embedding)
                if score >= self._min_score:
                    scored.append(ScoredMemory(memory.record, score))
            else:
                score = keyword_overlap(query, memory.record.text)
                if score > 0:
                    scored.append(ScoredMemory(memory.record, score))
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:limit]

    async def relevant(self, query: str) -> list[str]:
        """Texts of the memories worth adding to the prompt for ``query``.

        Never raises: memory is a nice-to-have and must not break a turn.
        """
        try:
            return [m.record.text for m in await self.recall(query)]
        except Exception:
            log.warning("memory_recall_failed", exc_info=True)
            return []

    async def all(self) -> list[MemoryRecord]:
        """Every memory, newest first."""
        return [m.record for m in await self._store.all()]

    async def forget(self, memory_id: int) -> bool:
        """Delete a memory by id."""
        return await self._store.delete(memory_id)

    async def _embed(self, text: str) -> list[float] | None:
        if self._embedder is None or self._embedder_failed:
            return None
        try:
            [vector] = await self._embedder.embed([text])
            return vector
        except Exception as exc:
            # Typically: the embedding model isn't pulled. Degrade to keywords.
            self._embedder_failed = True
            log.warning("embedding_unavailable", error=str(exc), fallback="keyword search")
            return None
