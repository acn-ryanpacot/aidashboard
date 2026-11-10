"""Local LLM and embeddings via `Ollama <https://ollama.com>`_ — free, private, offline."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import structlog

from jarvis_core.domain.errors import LanguageModelError
from jarvis_core.domain.models import ChatMessage, LlmEvent, Role, TextDelta, ToolCall, ToolSpec

log = structlog.get_logger(__name__)


def _client(base_url: str, timeout_s: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(timeout_s, connect=5.0))


def _wire_message(message: ChatMessage) -> dict[str, Any]:
    """Convert a domain message to Ollama's chat format."""
    wire: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.tool_calls:
        wire["tool_calls"] = [
            {"function": {"name": call.name, "arguments": dict(call.arguments)}}
            for call in message.tool_calls
        ]
    if message.role is Role.TOOL and message.tool_name:
        wire["tool_name"] = message.tool_name
    return wire


def _wire_tool(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": dict(spec.parameters),
        },
    }


def _parse_tool_call(raw: dict[str, Any]) -> ToolCall | None:
    function = raw.get("function") or {}
    name = function.get("name")
    if not name:
        return None
    arguments = function.get("arguments") or {}
    if isinstance(arguments, str):  # some models emit a JSON string
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            arguments = {}
    return ToolCall(
        name=name, arguments=arguments if isinstance(arguments, dict) else {}, id=raw.get("id")
    )


async def _installed_models(client: httpx.AsyncClient) -> set[str]:
    tags = (await client.get("/api/tags")).json()
    return {m.get("name") for m in tags.get("models", [])}


def _is_installed(installed: set[str], model: str) -> bool:
    return bool(installed & {model, f"{model}:latest"})


class OllamaLanguageModel:
    """Streams chat completions (with tool calling) from Ollama's ``/api/chat``.

    Implements :class:`~jarvis_core.domain.ports.LanguageModel`.

    Args:
        base_url: Ollama server URL, e.g. ``http://127.0.0.1:11434``.
        model: Model tag, e.g. ``llama3.2:3b`` (must be pulled first, and must
            support tools for tool calling — most current instruct models do).
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
        self._client = client or _client(base_url, timeout_s)

    async def stream_chat(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[LlmEvent]:
        """Yield text deltas and tool calls.

        Raises:
            LanguageModelError: If Ollama is unreachable or returns an error.
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [_wire_message(m) for m in messages],
            "stream": True,
            "keep_alive": self._keep_alive,
            "options": {"temperature": self._temperature},
        }
        if tools:
            payload["tools"] = [_wire_tool(spec) for spec in tools]
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
                    message = chunk.get("message") or {}
                    if content := message.get("content"):
                        yield TextDelta(content)
                    for raw_call in message.get("tool_calls") or ():
                        if call := _parse_tool_call(raw_call):
                            yield call
                    if chunk.get("done"):
                        break
        except httpx.HTTPError as exc:
            raise LanguageModelError("I can't reach my language model. Is Ollama running?") from exc

    async def warm_up(self) -> None:
        """Check the model is installed and load it into memory."""
        try:
            if not _is_installed(await _installed_models(self._client), self._model):
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
        if status == httpx.codes.BAD_REQUEST and "does not support tools" in body:
            return f"The model '{self._model}' doesn't support tools. Choose another model."
        return f"Ollama returned HTTP {status}: {body[:200]}"


class OllamaEmbeddingModel:
    """Text embeddings from Ollama's ``/api/embed``.

    Implements :class:`~jarvis_core.domain.ports.EmbeddingModel`.

    Args:
        base_url: Ollama server URL.
        model: Embedding model tag, e.g. ``nomic-embed-text``.
        client: Inject a custom :class:`httpx.AsyncClient` (used by tests).
    """

    def __init__(
        self, *, base_url: str, model: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self._model = model
        self._client = client or _client(base_url, 60.0)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed ``texts`` in one request.

        Raises:
            LanguageModelError: If the request fails (e.g. model not pulled).
        """
        try:
            response = await self._client.post(
                "/api/embed", json={"model": self._model, "input": list(texts)}
            )
        except httpx.HTTPError as exc:
            raise LanguageModelError("Ollama is unreachable for embeddings.") from exc
        if response.status_code != httpx.codes.OK:
            raise LanguageModelError(
                f"Embedding failed (HTTP {response.status_code}). "
                f"Is '{self._model}' pulled? Run: ollama pull {self._model}"
            )
        embeddings = response.json().get("embeddings") or []
        if len(embeddings) != len(texts):
            raise LanguageModelError("Ollama returned an unexpected number of embeddings.")
        return [[float(x) for x in vector] for vector in embeddings]

    async def warm_up(self) -> None:
        """Warn early if the embedding model is missing."""
        try:
            if not _is_installed(await _installed_models(self._client), self._model):
                log.warning(
                    "embedding_model_missing",
                    model=self._model,
                    hint=f"ollama pull {self._model} (memory falls back to keyword search)",
                )
        except httpx.HTTPError:
            pass

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._client.aclose()
