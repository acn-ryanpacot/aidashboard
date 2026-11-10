"""Semantic search over a folder of Markdown / text files (local RAG)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from jarvis_core.adapters.documents.chunking import chunk_text
from jarvis_core.adapters.persistence.repositories import SqliteDocumentChunkStore
from jarvis_core.application.vectors import cosine_similarity
from jarvis_core.domain.ports import EmbeddingModel
from jarvis_core.domain.records import DocumentHit

log = structlog.get_logger(__name__)

SUPPORTED_SUFFIXES = frozenset({".md", ".markdown", ".txt", ".rst", ".org"})
_EMBED_BATCH = 16


class FolderDocumentIndex:
    """Implements :class:`~jarvis_core.domain.ports.DocumentSearch`.

    Files are chunked, embedded with the configured embedding model and
    cached in SQLite. :meth:`refresh` only re-embeds files whose modification
    time changed, so restarts are cheap.

    Args:
        folder: Root folder to index (searched recursively).
        store: Chunk persistence.
        embedder: Embedding model.
        min_score: Minimum cosine similarity for a hit.
        max_file_bytes: Skip files larger than this.
    """

    def __init__(
        self,
        folder: Path,
        store: SqliteDocumentChunkStore,
        embedder: EmbeddingModel,
        *,
        min_score: float = 0.35,
        max_file_bytes: int = 2_000_000,
    ) -> None:
        self._folder = folder
        self._store = store
        self._embedder = embedder
        self._min_score = min_score
        self._max_file_bytes = max_file_bytes
        self._refresh_task: asyncio.Task[int] | None = None

    async def refresh(self) -> int:
        """Bring the index up to date; return how many files were (re)indexed."""
        if not self._folder.is_dir():
            log.warning("documents_folder_missing", folder=str(self._folder))
            return 0
        on_disk = await asyncio.to_thread(self._scan)
        indexed = await self._store.indexed_files()
        for stale in indexed.keys() - on_disk.keys():
            await self._store.remove_file(stale)

        updated = 0
        for path, mtime in sorted(on_disk.items()):
            if indexed.get(path) == mtime:
                continue
            try:
                text = await asyncio.to_thread(
                    Path(path).read_text, encoding="utf-8", errors="ignore"
                )
                chunks = chunk_text(text)
                vectors: list[list[float]] = []
                for start in range(0, len(chunks), _EMBED_BATCH):
                    vectors += await self._embedder.embed(chunks[start : start + _EMBED_BATCH])
                await self._store.replace_file(path, mtime, list(zip(chunks, vectors, strict=True)))
                updated += 1
            except Exception:
                log.warning("document_index_failed", path=path, exc_info=True)
        log.info("documents_indexed", folder=str(self._folder), updated=updated, total=len(on_disk))
        return updated

    def start_background_refresh(self) -> None:
        """Index in the background so startup isn't delayed by large folders."""
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self.refresh(), name="jarvis-doc-index")

    async def warm_up(self) -> None:
        """Container hook: start indexing without delaying start-up."""
        self.start_background_refresh()

    async def search(self, query: str, limit: int = 4) -> list[DocumentHit]:
        """Best-matching passages for ``query``."""
        chunks = await self._store.all_chunks()
        if not chunks:
            return []
        [query_vector] = await self._embedder.embed([query])
        hits = [
            DocumentHit(path=self._relative(path), text=text, score=score)
            for path, text, vector in chunks
            if (score := cosine_similarity(query_vector, vector)) >= self._min_score
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    async def aclose(self) -> None:
        """Stop any in-flight background indexing."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()

    def _scan(self) -> dict[str, float]:
        return {
            str(path): path.stat().st_mtime
            for path in self._folder.rglob("*")
            if path.suffix.lower() in SUPPORTED_SUFFIXES
            and path.is_file()
            and path.stat().st_size <= self._max_file_bytes
        }

    def _relative(self, path: str) -> str:
        try:
            return str(Path(path).relative_to(self._folder))
        except ValueError:
            return path
