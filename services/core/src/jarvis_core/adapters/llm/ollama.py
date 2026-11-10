"""Local LLM via `Ollama <https://ollama.com>`_ — free, private, offline."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence

import httpx
import structlog

from jarvis_core.domain.errors import LanguageModelError
from jarvis_core.domain.models import ChatMessage

log = structlog.get_logger(__name__)


class OllamaLanguageModel:
    """Streams chat completions from Ollama's ``/api/chat`` endpoint.

    Implements :class:`~jarvis_core.domain.ports.LanguageModel`.

    Args:
        base_url: Ollama server URL, e.g. ``http://127.0.0.1:11434``.
        model: Model tag, e.g. ``llama3.2:3b`` (must be pulled first).
        temperature: Sampling temperature.
        timeout_s: Read timeout for a whole response.
        keep_alive: How long Ollama keeps the model loaded between requests.
        client: Inject a custom :class:`httpx.AsyncClient` (used by tests).
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        temperature: float = 0.6,
        timeout_s: float = 120.0,
        keep_alive: str = "30m",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._keep_alive = keep_alive
        self._client = client or httpx.AsyncClient(
            base_url=base_url, timeout=httpx.Timeout(timeout_s, connect=5.0)
        )

    async def stream_chat(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        """Yield the reply as text deltas.

        Raises:
            LanguageModelError: If Ollama is unreachable or returns an error.
        """
        payload = {
            "model": self._model,
            "messages": [{"role": m.role.value, "content": m.content} for m in messages],
            "stream": True,
            "keep_alive": self._keep_alive,
            "options": {"temperature": self._temperature},
        }
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as response:
                if response.status_code != httpx.codes.OK:
                    body = (await response.aread()).decode(errors="replace")
                    raise LanguageModelError(self._describe_http_error(response.status_code, body))
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if error := chunk.get("error"):
                        raise LanguageModelError(f"Ollama error: {error}")
                    if content := chunk.get("message", {}).get("content"):
                        yield content
                    if chunk.get("done"):
                        break
        except httpx.HTTPError as exc:
            raise LanguageModelError("I can't reach my language model. Is Ollama running?") from exc

    async def warm_up(self) -> None:
        """Check the model is installed and load it into memory."""
        try:
            tags = (await self._client.get("/api/tags")).json()
            installed = {m.get("name") for m in tags.get("models", [])}
            if not installed & {self._model, f"{self._model}:latest"}:
                log.warning("ollama_model_missing", model=self._model, hint="ollama pull <model>")
                return
            await self._client.post(
                "/api/generate", json={"model": self._model, "keep_alive": self._keep_alive}
            )
            log.info("ollama_ready", model=self._model)
        except httpx.HTTPError as exc:
            log.warning("ollama_unreachable", error=str(exc))

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._client.aclose()

    def _describe_http_error(self, status: int, body: str) -> str:
        if status == httpx.codes.NOT_FOUND:
            return f"The model '{self._model}' isn't installed. Run: ollama pull {self._model}"
        return f"Ollama returned HTTP {status}: {body[:200]}"
