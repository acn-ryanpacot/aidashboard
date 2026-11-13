"""The user's documents folder: semantic search (local RAG) and spreadsheets.

Notes, PDFs, Word documents and spreadsheets are read locally (see
:mod:`~jarvis_core.adapters.documents.extractors`), split into passages,
embedded with the local embedding model and cached in SQLite. Nothing leaves
the machine.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import structlog

from jarvis_core.adapters.documents.chunking import chunk_text
from jarvis_core.adapters.documents.extractors import (
    SUPPORTED_SUFFIXES,
    UnreadableDocumentError,
    extract_text,
    kind_of,
    read_tables,
)
from jarvis_core.adapters.persistence.repositories import SqliteDocumentChunkStore
from jarvis_core.application.vectors import cosine_similarity
from jarvis_core.domain.errors import JarvisError
from jarvis_core.domain.ports import EmbeddingModel
from jarvis_core.domain.records import DocumentFile, DocumentHit, DocumentsStatus, SheetTable

__all__ = ["SUPPORTED_SUFFIXES", "FolderDocumentIndex"]

log = structlog.get_logger(__name__)

_EMBED_BATCH = 16
#: Plain-text notes above this size are skipped (they're rarely notes).
MAX_TEXT_BYTES = 2_000_000
#: PDFs, Word files and spreadsheets above this size are skipped.
MAX_BINARY_BYTES = 40_000_000
#: Passages kept per file, so one huge PDF can't dominate the index.
MAX_CHUNKS_PER_FILE = 600
_SKIPPED_FOLDERS = frozenset({"node_modules", "__pycache__"})


@dataclass(frozen=True, slots=True)
class _OnDisk:
    mtime: float
    size: int


class FolderDocumentIndex:
    """Implements :class:`~jarvis_core.domain.ports.DocumentLibrary`.

    :meth:`refresh` only re-reads files whose modification time changed, so
    restarts and the periodic re-scan are cheap.

    Args:
        folder: Root folder to index (searched recursively); ``""`` = none yet.
        store: Chunk persistence.
        embedder: Embedding model.
        min_score: Minimum cosine similarity for a hit.
        rescan_s: How often to look for new or changed files (0 = never).
    """

    def __init__(
        self,
        folder: Path | str,
        store: SqliteDocumentChunkStore,
        embedder: EmbeddingModel,
        *,
        min_score: float = 0.35,
        rescan_s: float = 300.0,
    ) -> None:
        self._folder = _as_folder(folder)
        self._store = store
        self._embedder = embedder
        self._min_score = min_score
        self._rescan_s = rescan_s
        self._lock = asyncio.Lock()
        self._refresh_task: asyncio.Task[int] | None = None
        self._watch_task: asyncio.Task[None] | None = None
        self._problems: dict[str, tuple[float, str]] = {}
        self._last_indexed: datetime | None = None
        self._error: str | None = None
        self._listeners: list[Callable[[], Awaitable[None]]] = []

    # ------------------------------------------------------------ settings

    @property
    def folder(self) -> str:
        """The configured folder, or ``""``."""
        return str(self._folder) if self._folder else ""

    def set_folder(self, folder: str) -> None:
        """Switch folders; passages from the old one are dropped on the next refresh."""
        new = _as_folder(folder)
        if new == self._folder:
            return
        self._folder = new
        self._problems.clear()
        self._error = None
        self._last_indexed = None
        log.info("documents_folder_changed", folder=self.folder or None)
        self._start_refresh(force=False)

    def on_change(self, listener: Callable[[], Awaitable[None]]) -> None:
        """Call ``listener`` whenever indexing starts or finishes."""
        self._listeners.append(listener)

    # ------------------------------------------------------------- indexing

    async def refresh(self, *, force: bool = False) -> int:
        """Bring the index up to date; return how many files were (re)indexed.

        Args:
            force: Re-read every file, even unchanged ones.
        """
        async with self._lock:
            await self._notify()
            try:
                return await self._refresh(force)
            finally:
                self._last_indexed = datetime.now(UTC)
                await self._notify()

    async def _refresh(self, force: bool) -> int:
        folder = self._folder
        on_disk = await asyncio.to_thread(self._scan, folder) if folder else {}
        if folder and not folder.is_dir():
            log.warning("documents_folder_missing", folder=str(folder))
        indexed = await self._store.indexed_files()
        for stale in indexed.keys() - on_disk.keys():
            await self._store.remove_file(stale)

        updated = 0
        embed_failures = 0
        for path, info in sorted(on_disk.items()):
            if not force and indexed.get(path) == info.mtime:
                continue
            known = self._problems.get(path)
            if not force and known is not None and known[0] == info.mtime:
                continue
            name = self._relative(path)
            try:
                text = await asyncio.to_thread(extract_text, Path(path), name)
            except UnreadableDocumentError as exc:
                self._problems[path] = (info.mtime, str(exc))
                await self._store.remove_file(path)
                log.info("document_unreadable", path=name, reason=str(exc))
                continue
            chunks = chunk_text(text)[:MAX_CHUNKS_PER_FILE]
            try:
                vectors = await self._embed([f"{name}\n{chunk}" for chunk in chunks])
            except Exception as exc:
                embed_failures += 1
                self._error = f"The embedding model isn't available ({_reason(exc)})."
                log.warning("document_embedding_failed", path=name, exc_info=True)
                if embed_failures >= 3 and updated == 0:
                    break  # every file would fail the same way
                continue
            await self._store.replace_file(
                path, info.mtime, list(zip(chunks, vectors, strict=True))
            )
            self._problems.pop(path, None)
            updated += 1
        if embed_failures == 0:
            self._error = None
        self._problems = {p: v for p, v in self._problems.items() if p in on_disk}
        log.info("documents_indexed", folder=self.folder, updated=updated, total=len(on_disk))
        return updated

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH):
            vectors += await self._embedder.embed(texts[start : start + _EMBED_BATCH])
        return vectors

    def reindex(self) -> None:
        """Re-read every file in the background."""
        self._start_refresh(force=True)

    def start_background_refresh(self) -> None:
        """Index in the background so startup isn't delayed by large folders."""
        self._start_refresh(force=False)

    def _start_refresh(self, *, force: bool) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # not started yet; warm_up indexes
        if force or self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(
                self.refresh(force=force), name="jarvis-doc-index"
            )

    async def warm_up(self) -> None:
        """Container hook: index in the background, then re-scan periodically."""
        self.start_background_refresh()
        if self._rescan_s > 0 and self._watch_task is None:
            self._watch_task = asyncio.create_task(self._watch(), name="jarvis-doc-watch")

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(self._rescan_s)
            if self._folder is not None:
                try:
                    await self.refresh()
                except Exception:
                    log.warning("document_rescan_failed", exc_info=True)

    async def aclose(self) -> None:
        """Stop any in-flight background indexing."""
        for task in (self._refresh_task, self._watch_task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    # -------------------------------------------------------------- reading

    async def search(self, query: str, limit: int = 4) -> list[DocumentHit]:
        """Best-matching passages for ``query`` from the current folder."""
        if self._folder is None:
            return []
        chunks = [c for c in await self._store.all_chunks() if self._inside(c[0])]
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

    async def spreadsheets(self) -> list[str]:
        """Relative paths of the spreadsheets in the folder."""
        if self._folder is None:
            return []
        on_disk = await asyncio.to_thread(self._scan, self._folder)
        return sorted(
            self._relative(path) for path in on_disk if kind_of(Path(path)) == "spreadsheet"
        )

    async def tables(self, path: str) -> list[SheetTable]:
        """The sheets of the spreadsheet at relative ``path``."""
        if self._folder is None:
            raise JarvisError("No documents folder is set.")
        full = (self._folder / path).resolve()
        if not full.is_relative_to(self._folder.resolve()) or not full.is_file():
            raise JarvisError(f"There's no spreadsheet called {path}.")
        try:
            return await asyncio.to_thread(read_tables, full, path)
        except UnreadableDocumentError as exc:
            raise JarvisError(f"{path}: {exc}.") from exc
        except Exception as exc:
            raise JarvisError(f"{path} couldn't be read.") from exc

    async def status(self) -> DocumentsStatus:
        """Folder, files and indexing progress."""
        folder = self._folder
        if folder is None:
            return DocumentsStatus(folder="", exists=False, indexing=self._lock.locked())
        on_disk = await asyncio.to_thread(self._scan, folder)
        counts = await self._store.chunk_counts()
        files = tuple(
            DocumentFile(
                path=self._relative(path),
                kind=kind_of(Path(path)) or "text",
                size=info.size,
                modified=datetime.fromtimestamp(info.mtime, UTC),
                chunks=counts.get(path, 0),
                problem=(self._problems.get(path) or (0.0, None))[1],
            )
            for path, info in sorted(on_disk.items())
        )
        return DocumentsStatus(
            folder=str(folder),
            exists=folder.is_dir(),
            indexing=self._lock.locked(),
            files=files,
            last_indexed=self._last_indexed,
            error=self._error,
        )

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _scan(folder: Path) -> dict[str, _OnDisk]:
        if not folder.is_dir():
            return {}
        found: dict[str, _OnDisk] = {}
        for path in folder.rglob("*"):
            kind = kind_of(path)
            if kind is None or path.name.startswith(("~$", ".")):
                continue  # ~$ = Office lock files
            relative = path.relative_to(folder).parts[:-1]
            if any(part.startswith(".") or part in _SKIPPED_FOLDERS for part in relative):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            limit = MAX_TEXT_BYTES if kind == "text" else MAX_BINARY_BYTES
            if path.is_file() and stat.st_size <= limit:
                found[str(path)] = _OnDisk(stat.st_mtime, stat.st_size)
        return found

    def _inside(self, path: str) -> bool:
        return self._folder is not None and Path(path).is_relative_to(self._folder)

    def _relative(self, path: str) -> str:
        if self._folder is None:
            return path
        try:
            return Path(path).relative_to(self._folder).as_posix()
        except ValueError:
            return path

    async def _notify(self) -> None:
        for listener in self._listeners:
            try:
                await listener()
            except Exception:
                log.warning("documents_listener_failed", exc_info=True)


def _as_folder(folder: Path | str) -> Path | None:
    text = str(folder).strip().strip('"').strip()
    return Path(text).expanduser() if text else None


def _reason(exc: Exception) -> str:
    text = str(exc).strip() or type(exc).__name__
    return text if len(text) <= 120 else text[:117] + "…"
