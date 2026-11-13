"""Web search: provider fallback, privacy redaction and reading result pages."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlparse

import structlog

from jarvis_core.domain.errors import JarvisError
from jarvis_core.domain.ports import PageReader, WebSearchProvider
from jarvis_core.domain.records import SearchResult

log = structlog.get_logger(__name__)

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b")
#: Seven or more digits, optionally grouped by spaces or dashes: card, account,
#: phone and ID numbers. Prices ("1,500") and years ("2026") are untouched.
_LONG_NUMBER = re.compile(r"(?<![\w,.])\d(?:[ -]?\d){6,}(?![\w,.])")
_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    [
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "is",
        "are",
        "was",
        "were",
        "what",
        "who",
        "when",
        "where",
        "how",
        "why",
        "which",
        "does",
        "do",
        "did",
        "can",
        "could",
        "will",
        "would",
        "about",
        "with",
        "from",
        "that",
        "this",
        "it",
        "its",
        "be",
        "by",
        "at",
        "as",
        "me",
        "my",
        "you",
        "your",
        "please",
        "tell",
        "find",
        "search",
        "look",
        "up",
        "latest",
    ]
)
PAGES_READ = 2
PAGE_TIMEOUT_S = 5.0
PASSAGE_CHARS = 450


def redact_query(query: str) -> str:
    """Remove e-mail addresses and long ID-like numbers from a search query.

    The model is told never to put personal details in a web search; this
    catches the obvious leaks (account, card and phone numbers, e-mails) if it
    does anyway.
    """
    cleaned = _LONG_NUMBER.sub(" ", _EMAIL.sub(" ", query))
    return " ".join(cleaned.split())


@dataclass(frozen=True, slots=True)
class PageExtract:
    """The most relevant text of one result page."""

    result: SearchResult
    passages: tuple[str, ...]


class FallbackWebSearch:
    """Implements :class:`~jarvis_core.domain.ports.WebSearchProvider` over several providers.

    Providers are tried in order; the first one that answers wins. An empty
    answer is final (the web simply has nothing), an error moves on.

    Args:
        providers: E.g. SearXNG first, then DuckDuckGo.
    """

    def __init__(self, providers: Sequence[WebSearchProvider]) -> None:
        if not providers:
            raise ValueError("at least one provider is needed")
        self._providers = list(providers)

    @property
    def label(self) -> str:
        """Provider names, e.g. ``SearXNG, then DuckDuckGo``."""
        return ", then ".join(getattr(p, "label", type(p).__name__) for p in self._providers)

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Top results from the first provider that answers."""
        error: JarvisError | None = None
        for provider in self._providers:
            try:
                return await provider.search(query, limit)
            except JarvisError as exc:
                log.info("web_search_provider_failed", provider=type(provider).__name__)
                error = exc
        assert error is not None
        raise error

    async def aclose(self) -> None:
        """Close every provider."""
        for provider in self._providers:
            close = getattr(provider, "aclose", None)
            if close is not None:
                await close()


def keywords(text: str) -> set[str]:
    """Meaningful lowercase words of ``text``."""
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 1}


def best_passages(text: str, query: str, count: int = 2) -> list[str]:
    """The ``count`` paragraphs of ``text`` that share the most words with ``query``.

    Paragraphs shorter than 60 characters (menus, captions, buttons) are ignored.
    """
    wanted = keywords(query)
    if not wanted:
        return []
    scored = []
    for position, paragraph in enumerate(text.splitlines()):
        paragraph = paragraph.strip()
        if len(paragraph) < 60:
            continue
        overlap = len(wanted & keywords(paragraph))
        if overlap:
            scored.append((overlap, -position, paragraph))
    scored.sort(reverse=True)
    chosen = sorted(scored[:count], key=lambda item: -item[1])
    return [_clip(paragraph, PASSAGE_CHARS) for _, _, paragraph in chosen]


async def read_top_pages(
    reader: PageReader, results: Sequence[SearchResult], query: str
) -> list[PageExtract]:
    """Read the first :data:`PAGES_READ` result pages in parallel (errors skipped)."""

    async def one(result: SearchResult) -> PageExtract | None:
        try:
            text = await asyncio.wait_for(reader.read(result.url), PAGE_TIMEOUT_S)
        except (JarvisError, TimeoutError):
            return None
        except Exception:
            log.info("web_page_read_failed", url=domain(result.url), exc_info=True)
            return None
        passages = best_passages(text, query)
        return PageExtract(result, tuple(passages)) if passages else None

    extracts = await asyncio.gather(*(one(r) for r in results[:PAGES_READ]))
    return [extract for extract in extracts if extract is not None]


def describe_results(results: Sequence[SearchResult], pages: Sequence[PageExtract] = ()) -> str:
    """Tool output: numbered results with their site, then passages read from pages."""
    lines = ["Web results (cite the site when you answer):"]
    lines += [
        f"{i}. {r.title} ({domain(r.url)}): {r.snippet}" for i, r in enumerate(results, start=1)
    ]
    for page in pages:
        lines.append(f"From {domain(page.result.url)}: " + " … ".join(page.passages))
    return "\n".join(lines)


def domain(url: str) -> str:
    """``www.rappler.com`` → ``rappler.com``."""
    host = urlparse(url).hostname or url
    return host.removeprefix("www.")


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"
