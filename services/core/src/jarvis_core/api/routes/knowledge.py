"""Where Jarvis gets answers beyond his own knowledge: web search and your documents.

``GET /api/knowledge`` reports both for Settings → Knowledge;
``POST /api/documents/reindex`` re-reads the documents folder.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from jarvis_core.container import Container
from jarvis_core.domain.records import DocumentFile

router = APIRouter(prefix="/api", tags=["knowledge"])

#: Files listed in the response (the counts always cover every file).
MAX_FILES_LISTED = 300


def _container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


class DocumentFileOut(BaseModel):
    """One file in the documents folder."""

    path: str
    kind: str
    size: int
    modified: datetime
    chunks: int
    problem: str | None

    @classmethod
    def of(cls, file: DocumentFile) -> DocumentFileOut:
        """Build from the domain record."""
        return cls(
            path=file.path,
            kind=file.kind,
            size=file.size,
            modified=file.modified,
            chunks=file.chunks,
            problem=file.problem,
        )


class DocumentsOut(BaseModel):
    """The documents folder and its index."""

    available: bool
    folder: str
    exists: bool
    indexing: bool
    total: int
    indexed: int
    by_kind: dict[str, int]
    files: list[DocumentFileOut]
    last_indexed: datetime | None
    error: str | None


class WebSearchOut(BaseModel):
    """Which web search Jarvis uses."""

    enabled: bool
    provider: str
    mode: Literal["auto", "searxng", "duckduckgo", "off"]
    searxng: bool
    reads_pages: bool


class KnowledgeOut(BaseModel):
    """Both sources together."""

    documents: DocumentsOut
    web: WebSearchOut


async def _documents(container: Container) -> DocumentsOut:
    library = container.documents
    if library is None:
        return DocumentsOut(
            available=False,
            folder="",
            exists=False,
            indexing=False,
            total=0,
            indexed=0,
            by_kind={},
            files=[],
            last_indexed=None,
            error="Document search needs tools and the embedding model (nomic-embed-text).",
        )
    state = await library.status()
    return DocumentsOut(
        available=True,
        folder=state.folder,
        exists=state.exists,
        indexing=state.indexing,
        total=len(state.files),
        indexed=sum(1 for f in state.files if f.chunks),
        by_kind=dict(Counter(f.kind for f in state.files)),
        files=[DocumentFileOut.of(f) for f in state.files[:MAX_FILES_LISTED]],
        last_indexed=state.last_indexed,
        error=state.error,
    )


@router.get("/knowledge", response_model=KnowledgeOut)
async def get_knowledge(request: Request) -> KnowledgeOut:
    """Web search provider and the documents folder's index."""
    container = _container(request)
    s = container.settings
    return KnowledgeOut(
        documents=await _documents(container),
        web=WebSearchOut(
            enabled=bool(container.web_search),
            provider=container.web_search,
            mode=s.web_search,
            searxng=bool(s.searxng_url) and s.web_search in {"auto", "searxng"},
            reads_pages=s.web_read_pages,
        ),
    )


@router.post("/documents/reindex", response_model=DocumentsOut, status_code=202)
async def reindex_documents(request: Request) -> DocumentsOut:
    """Re-read every file in the documents folder (in the background)."""
    container = _container(request)
    if container.documents is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document search isn't available.")
    container.documents.reindex()
    await asyncio.sleep(0)  # let the refresh start, so the reply says so
    return await _documents(container)
