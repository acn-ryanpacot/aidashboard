"""Encyclopedia lookups via the public Wikipedia REST API (free, no key)."""

from __future__ import annotations

from urllib.parse import quote

import httpx

from jarvis_core.domain.errors import JarvisError
from jarvis_core.domain.records import KnowledgeArticle

SEARCH_URL = "https://en.wikipedia.org/w/api.php"
SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
#: Wikimedia's robot policy requires a descriptive User-Agent with a contact URL
#: or email (https://w.wiki/4wJS); generic ones get HTTP 403.
DEFAULT_USER_AGENT = (
    "JarvisOS/0.2 (+https://localhost; self-hosted personal assistant) python-httpx"
)


class WikipediaKnowledgeProvider:
    """Implements :class:`~jarvis_core.domain.ports.KnowledgeProvider`.

    Searches for the best-matching article, then fetches its lead summary.

    Args:
        max_chars: Truncate summaries to keep prompts small.
        user_agent: Sent with every request; ideally include your own contact URL.
        client: Inject a custom :class:`httpx.AsyncClient` (used by tests).
    """

    def __init__(
        self,
        *,
        max_chars: int = 900,
        user_agent: str = DEFAULT_USER_AGENT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._max_chars = max_chars
        self._client = client or httpx.AsyncClient(
            timeout=10.0, headers={"User-Agent": user_agent}, follow_redirects=True
        )

    async def lookup(self, topic: str) -> KnowledgeArticle | None:
        """Summary of the article that best matches ``topic``."""
        try:
            search = await self._client.get(
                SEARCH_URL,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": topic,
                    "srlimit": 1,
                    "format": "json",
                },
            )
            search.raise_for_status()
            hits = search.json().get("query", {}).get("search", [])
            if not hits:
                return None
            title = hits[0]["title"]
            summary = await self._client.get(
                SUMMARY_URL.format(title=quote(title.replace(" ", "_")))
            )
            summary.raise_for_status()
            data = summary.json()
        except httpx.HTTPError as exc:
            raise JarvisError("The encyclopedia is unreachable right now.") from exc

        extract = (data.get("extract") or "").strip()
        if not extract:
            return None
        if len(extract) > self._max_chars:
            extract = extract[: self._max_chars].rsplit(" ", 1)[0] + "…"
        url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        return KnowledgeArticle(title=data.get("title", title), summary=extract, url=url)

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._client.aclose()
