"""Web search through DuckDuckGo's HTML results page: no key, no setup.

This is the fallback when no SearXNG server is running. DuckDuckGo doesn't
offer an official search API, so this reads the plain-HTML results page
(``html.duckduckgo.com``) the way a text browser would. It is free and
private (DuckDuckGo doesn't profile searches), but it can be rate-limited or
change without notice, which is why SearXNG stays the recommended route
(``docs/guides/web-search.md``).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import httpx

from jarvis_core.domain.errors import JarvisError
from jarvis_core.domain.records import SearchResult

#: A generic desktop browser identity. The plain-HTML page refuses unknown clients.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
RATE_LIMITED = (
    "DuckDuckGo is limiting searches from this PC for a few minutes. "
    "Setting up SearXNG avoids this (docs/guides/web-search.md)."
)


class DuckDuckGoSearchProvider:
    """Implements :class:`~jarvis_core.domain.ports.WebSearchProvider`.

    When DuckDuckGo answers with a captcha (it thinks the searches are
    automated), the provider respects that and makes no requests at all for
    ``cooldown_s``; searches fail fast with a clear message meanwhile.

    Args:
        region: DuckDuckGo region code, e.g. ``ph-en`` or ``wt-wt`` (worldwide).
        client: Inject a custom :class:`httpx.AsyncClient` (used by tests).
        cooldown_s: How long to back off after a captcha.
        clock: Monotonic clock (tests).
    """

    label = "DuckDuckGo"

    def __init__(
        self,
        region: str = "wt-wt",
        client: httpx.AsyncClient | None = None,
        *,
        cooldown_s: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._region = region
        self._client = client or httpx.AsyncClient(
            base_url="https://html.duckduckgo.com",
            timeout=10.0,
            headers={"User-Agent": BROWSER_USER_AGENT, "Accept-Language": "en"},
            follow_redirects=True,
        )
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._blocked_until = 0.0

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Top results for ``query``."""
        if self._clock() < self._blocked_until:
            raise JarvisError(RATE_LIMITED)
        try:
            response = await self._client.post("/html/", data={"q": query, "kl": self._region})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise JarvisError("Web search is unavailable right now.") from exc
        if response.status_code == 202 or "anomaly-modal" in response.text:
            self._blocked_until = self._clock() + self._cooldown_s
            raise JarvisError(RATE_LIMITED)
        return parse_results(response.text)[:limit]

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._client.aclose()


def parse_results(html: str) -> list[SearchResult]:
    """Results from DuckDuckGo's HTML page, ads removed."""
    parser = _ResultParser()
    parser.feed(html)
    parser.close()
    results = []
    seen: set[str] = set()
    for title, url, snippet in parser.results:
        target = _target(url)
        if not title or target is None or target in seen:
            continue
        seen.add(target)
        results.append(SearchResult(title=title, snippet=snippet[:300], url=target))
    return results


def _target(href: str) -> str | None:
    """The real address behind a DuckDuckGo redirect link; ``None`` for ads."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com"):
        if parsed.path.startswith("/y.js"):
            return None  # an advert
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        parsed = urlparse(target)
        href = target
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return href


class _ResultParser(HTMLParser):
    """Collects (title, href, snippet) from ``result__a`` / ``result__snippet``."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[tuple[str, str, str]] = []
        self._field: str | None = None
        self._tag = ""
        self._depth = 0
        self._text: list[str] = []
        self._href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._field is not None:
            if tag == self._tag:
                self._depth += 1
            return
        classes = (dict(attrs).get("class") or "").split()
        if tag == "a" and "result__a" in classes:
            self._begin("title", tag)
            self._href = dict(attrs).get("href") or ""
        elif "result__snippet" in classes and self.results:
            self._begin("snippet", tag)

    def handle_endtag(self, tag: str) -> None:
        if self._field is None or tag != self._tag:
            return
        if self._depth:
            self._depth -= 1
            return
        text = " ".join("".join(self._text).split())
        if self._field == "title":
            self.results.append((text, self._href, ""))
        else:
            title, href, _ = self.results[-1]
            self.results[-1] = (title, href, text)
        self._field = None

    def handle_data(self, data: str) -> None:
        if self._field is not None:
            self._text.append(data)

    def _begin(self, field: str, tag: str) -> None:
        self._field, self._tag, self._depth, self._text = field, tag, 0, []
