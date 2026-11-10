"""Headlines from RSS 2.0, RSS 1.0 (RDF) and Atom feeds — standard library only.

Python's bundled expat (≥ 2.4.1) is hardened against entity-expansion
("billion laughs") attacks, so parsing untrusted feeds with
:mod:`xml.etree.ElementTree` is acceptable here.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
import structlog

from jarvis_core.domain.records import Headline

log = structlog.get_logger(__name__)

ATOM = "{http://www.w3.org/2005/Atom}"
RSS1 = "{http://purl.org/rss/1.0/}"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
DC = "{http://purl.org/dc/elements/1.1/}"
USER_AGENT = "JarvisOS/0.3 (+https://localhost; self-hosted personal assistant) python-httpx"


def _rfc822(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value.strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _text(element: ET.Element | None) -> str:
    return " ".join((element.text or "").split()) if element is not None else ""


def parse_feed(data: bytes | str, fallback_source: str = "") -> list[Headline]:
    """Parse one feed document into headlines (newest first when dated).

    Args:
        data: The raw XML.
        fallback_source: Used when the feed has no title.

    Raises:
        ValueError: If the document isn't a recognisable feed.
    """
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"not valid XML: {exc}") from exc

    headlines: list[Headline] = []
    if root.tag == "rss":
        channel = root.find("channel")
        source = _text(channel.find("title")) if channel is not None else ""
        for item in root.iter("item"):
            headlines.append(
                Headline(
                    title=_text(item.find("title")),
                    source=source or fallback_source,
                    url=_text(item.find("link")),
                    published=_rfc822(item.findtext("pubDate")) or _iso(item.findtext(f"{DC}date")),
                )
            )
    elif root.tag == f"{ATOM}feed":
        source = _text(root.find(f"{ATOM}title"))
        for entry in root.iter(f"{ATOM}entry"):
            links = entry.findall(f"{ATOM}link")
            href = next(
                (
                    link.get("href", "")
                    for link in links
                    if link.get("rel", "alternate") == "alternate"
                ),
                links[0].get("href", "") if links else "",
            )
            headlines.append(
                Headline(
                    title=_text(entry.find(f"{ATOM}title")),
                    source=source or fallback_source,
                    url=href,
                    published=_iso(entry.findtext(f"{ATOM}updated"))
                    or _iso(entry.findtext(f"{ATOM}published")),
                )
            )
    elif root.tag == f"{RDF}RDF":
        channel = root.find(f"{RSS1}channel")
        source = _text(channel.find(f"{RSS1}title")) if channel is not None else ""
        for item in root.iter(f"{RSS1}item"):
            headlines.append(
                Headline(
                    title=_text(item.find(f"{RSS1}title")),
                    source=source or fallback_source,
                    url=_text(item.find(f"{RSS1}link")),
                    published=_iso(item.findtext(f"{DC}date")),
                )
            )
    else:
        raise ValueError(f"unsupported feed type <{root.tag}>")
    return [h for h in headlines if h.title]


def merge_headlines(groups: Sequence[Sequence[Headline]], limit: int) -> list[Headline]:
    """Interleave feeds newest-first, dropping duplicate titles."""
    epoch = datetime.min.replace(tzinfo=UTC)
    merged = sorted(
        (h for group in groups for h in group), key=lambda h: h.published or epoch, reverse=True
    )
    seen: set[str] = set()
    unique: list[Headline] = []
    for headline in merged:
        key = headline.title.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(headline)
    return unique[:limit]


class RssNewsProvider:
    """Implements :class:`~jarvis_core.domain.ports.NewsProvider`.

    Feeds are fetched concurrently; a broken feed is logged and skipped.

    Args:
        client: Inject a custom :class:`httpx.AsyncClient` (used by tests).
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=10.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )

    async def headlines(self, feeds: Sequence[str], limit: int = 10) -> list[Headline]:
        """Newest headlines across ``feeds``."""
        results = await asyncio.gather(*(self._fetch(url) for url in feeds), return_exceptions=True)
        groups: list[list[Headline]] = []
        for url, result in zip(feeds, results, strict=True):
            if isinstance(result, BaseException):
                log.warning("feed_failed", url=url, error=str(result))
            else:
                groups.append(result)
        return merge_headlines(groups, limit)

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._client.aclose()

    async def _fetch(self, url: str) -> list[Headline]:
        response = await self._client.get(url)
        response.raise_for_status()
        return parse_feed(response.content, fallback_source=httpx.URL(url).host)
