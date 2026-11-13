"""Read the main text of a public web page, so answers aren't limited to snippets."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from jarvis_core.adapters.web.duckduckgo import BROWSER_USER_AGENT
from jarvis_core.domain.errors import JarvisError

MAX_PAGE_BYTES = 1_500_000
_SKIP = frozenset(
    {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "button"}
)
_BLOCK = frozenset(
    {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "td", "th", "tr", "br", "article",
     "section", "blockquote", "pre", "dd", "dt", "figcaption", "main"}
)  # fmt: skip


class HttpPageReader:
    """Implements :class:`~jarvis_core.domain.ports.PageReader`.

    Only public addresses are fetched: a search result pointing at
    ``localhost``, a LAN or Tailscale address is refused, so a web page can
    never be used to reach services on your own network.

    Args:
        client: Inject a custom :class:`httpx.AsyncClient` (used by tests).
        check_address: Resolve host names and refuse private addresses.
    """

    def __init__(
        self, client: httpx.AsyncClient | None = None, *, check_address: bool = True
    ) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=6.0,
            headers={"User-Agent": BROWSER_USER_AGENT, "Accept": "text/html,text/plain"},
            follow_redirects=False,
        )
        self._check_address = check_address

    async def read(self, url: str, *, redirects: int = 3) -> str:
        """Readable text of the page at ``url``."""
        if self._check_address and not await is_public_url(url):
            raise JarvisError("That address isn't a public web page.")
        try:
            async with self._client.stream("GET", url) as response:
                if response.is_redirect and redirects > 0:
                    target = str(response.url.join(response.headers.get("location", "")))
                    return await self.read(target, redirects=redirects - 1)
                response.raise_for_status()
                kind = response.headers.get("content-type", "")
                if "html" not in kind and "text/plain" not in kind:
                    raise JarvisError("That page isn't text.")
                body = bytearray()
                async for part in response.aiter_bytes():
                    body += part
                    if len(body) >= MAX_PAGE_BYTES:
                        break
                html = body.decode(response.encoding or "utf-8", errors="replace")
        except httpx.HTTPError as exc:
            raise JarvisError("The page couldn't be loaded.") from exc
        return page_text(html) if "html" in kind else html

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._client.aclose()


async def is_public_url(url: str) -> bool:
    """Whether ``url`` is http(s) and every address it resolves to is public."""
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    if host == "localhost" or host.endswith((".local", ".internal", ".lan", ".ts.net")):
        return False
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    except OSError:
        return False
    addresses = {info[4][0] for info in infos}
    return bool(addresses) and all(
        ipaddress.ip_address(str(address).split("%")[0]).is_global for address in addresses
    )


def page_text(html: str) -> str:
    """Visible text of an HTML page, one block per line, menus and scripts removed."""
    parser = _TextParser()
    parser.feed(html)
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self._skipping += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self._skipping:
            self._skipping -= 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)
