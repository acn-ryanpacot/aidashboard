"""Web search through a self-hosted `SearXNG <https://docs.searxng.org>`_ instance.

SearXNG is a free, private meta-search engine. Run one locally with Docker
(see ``docs/guides/web-search.md``) and set ``JARVIS_SEARXNG_URL``.
"""

from __future__ import annotations

import httpx

from jarvis_core.domain.errors import JarvisError
from jarvis_core.domain.records import SearchResult


class SearxngSearchProvider:
    """Implements :class:`~jarvis_core.domain.ports.WebSearchProvider`.

    Args:
        base_url: SearXNG URL, e.g. ``http://127.0.0.1:8888``. The instance must
            have the ``json`` output format enabled.
        client: Inject a custom :class:`httpx.AsyncClient` (used by tests).
    """

    label = "SearXNG"

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=12.0)

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Top results for ``query``."""
        try:
            response = await self._client.get(
                "/search", params={"q": query, "format": "json", "safesearch": 1}
            )
            response.raise_for_status()
            results = response.json().get("results") or []
        except (httpx.HTTPError, ValueError) as exc:
            raise JarvisError("Web search is unavailable right now.") from exc
        return [
            SearchResult(
                title=str(item.get("title", "")).strip(),
                snippet=str(item.get("content", "")).strip()[:300],
                url=str(item.get("url", "")),
            )
            for item in results[:limit]
            if item.get("title")
        ]

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._client.aclose()
