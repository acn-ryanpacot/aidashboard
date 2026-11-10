"""HTTP integrations (Ollama tools/embeddings, Open-Meteo, Wikipedia, SearXNG),
document indexing and the MCP tool bridge — all without the network."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from jarvis_core.adapters.documents.chunking import chunk_text
from jarvis_core.adapters.documents.folder_index import FolderDocumentIndex
from jarvis_core.adapters.llm.ollama import OllamaEmbeddingModel, OllamaLanguageModel
from jarvis_core.adapters.mcp.toolset import McpToolset, result_text, tool_name, wrap_tool
from jarvis_core.adapters.persistence.database import Database
from jarvis_core.adapters.persistence.repositories import SqliteDocumentChunkStore
from jarvis_core.adapters.web.open_meteo import OpenMeteoWeatherProvider
from jarvis_core.adapters.web.searxng import SearxngSearchProvider
from jarvis_core.adapters.web.wikipedia import WikipediaKnowledgeProvider
from jarvis_core.application.tools.registry import ToolError
from jarvis_core.domain.errors import JarvisError, LanguageModelError
from jarvis_core.domain.models import ChatMessage, Role, TextDelta, ToolCall, ToolSpec
from tests.fakes import FakeEmbedder

Handler = Callable[[httpx.Request], httpx.Response]


def client(handler: Handler, base_url: str = "http://test") -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, transport=httpx.MockTransport(handler))


def ndjson(*chunks: dict[str, Any]) -> str:
    return "\n".join(json.dumps(c) for c in chunks)


# -------------------------------------------------------------- Ollama


async def test_ollama_streams_tool_calls_and_sends_tools() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            text=ndjson(
                {"message": {"content": "One moment. "}},
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "get_weather",
                                    "arguments": {"location": "Oslo"},
                                }
                            },
                            {"function": {"name": "add_task", "arguments": '{"title": "Milk"}'}},
                            {"function": {"name": "", "arguments": {}}},
                        ],
                    }
                },
                {"message": {"content": ""}, "done": True},
            ),
        )

    llm = OllamaLanguageModel(base_url="http://test", model="m", client=client(handler))
    history = [
        ChatMessage(Role.USER, "hi"),
        ChatMessage(Role.ASSISTANT, "", (ToolCall("get_weather", {"location": "Oslo"}),)),
        ChatMessage(Role.TOOL, "Sunny", tool_name="get_weather"),
    ]
    spec = ToolSpec("get_weather", "Weather.", {"type": "object", "properties": {}})
    events = [e async for e in llm.stream_chat(history, [spec])]

    assert events == [
        TextDelta("One moment. "),
        ToolCall("get_weather", {"location": "Oslo"}),
        ToolCall("add_task", {"title": "Milk"}),
    ]
    assert seen["tools"][0]["function"]["name"] == "get_weather"
    assert seen["messages"][1]["tool_calls"][0]["function"]["arguments"] == {"location": "Oslo"}
    assert seen["messages"][2] == {"role": "tool", "content": "Sunny", "tool_name": "get_weather"}


async def test_ollama_explains_models_without_tool_support() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='{"error":"model does not support tools"}')

    llm = OllamaLanguageModel(base_url="http://test", model="tiny", client=client(handler))
    with pytest.raises(LanguageModelError, match="doesn't support tools"):
        _ = [e async for e in llm.stream_chat([], [ToolSpec("x", "")])]


async def test_ollama_embeddings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0]] * len(body["input"])})

    embedder = OllamaEmbeddingModel(base_url="http://test", model="e", client=client(handler))
    assert await embedder.embed(["a", "b"]) == [[1.0, 0.0], [1.0, 0.0]]

    failing = OllamaEmbeddingModel(
        base_url="http://test", model="e", client=client(lambda _: httpx.Response(404))
    )
    with pytest.raises(LanguageModelError, match="ollama pull e"):
        await failing.embed(["a"])


# ------------------------------------------------------------- weather


async def test_open_meteo_geocodes_then_forecasts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "geocoding" in request.url.host:
            if request.url.params["name"] == "Nowhere":
                return httpx.Response(200, json={})
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "Manila",
                            "country": "Philippines",
                            "latitude": 14.6,
                            "longitude": 121.0,
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "current": {
                    "temperature_2m": 30.2,
                    "apparent_temperature": 35.0,
                    "relative_humidity_2m": 70,
                    "weather_code": 61,
                    "wind_speed_10m": 9.5,
                },
                "daily": {"temperature_2m_max": [32.0], "temperature_2m_min": [26.0]},
            },
        )

    provider = OpenMeteoWeatherProvider(client(handler))
    report = await provider.current("Manila")
    assert report is not None
    assert (report.location, report.description, report.high_c) == (
        "Manila, Philippines",
        "light rain",
        32.0,
    )
    assert await provider.current("Nowhere") is None

    broken = OpenMeteoWeatherProvider(client(lambda _: httpx.Response(500)))
    with pytest.raises(JarvisError, match="unreachable"):
        await broken.current("Manila")


# ------------------------------------------------------------ knowledge


async def test_wikipedia_search_then_summary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("api.php"):
            return httpx.Response(200, json={"query": {"search": [{"title": "Alan Turing"}]}})
        assert request.url.path.endswith("/Alan_Turing")
        return httpx.Response(
            200,
            json={
                "title": "Alan Turing",
                "extract": "Alan Turing was a mathematician. " * 60,
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Alan_Turing"}},
            },
        )

    provider = WikipediaKnowledgeProvider(max_chars=120, client=client(handler))
    article = await provider.lookup("turing")
    assert article is not None and article.title == "Alan Turing"
    assert len(article.summary) <= 121 and article.summary.endswith("…")

    empty = WikipediaKnowledgeProvider(
        client=client(lambda _: httpx.Response(200, json={"query": {"search": []}}))
    )
    assert await empty.lookup("zzz") is None


async def test_searxng_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["format"] == "json"
        return httpx.Response(
            200,
            json={"results": [{"title": "A", "content": "first", "url": "u1"}, {"content": "x"}]},
        )

    provider = SearxngSearchProvider("http://search", client(handler, "http://search"))
    results = await provider.search("q")
    assert [(r.title, r.snippet) for r in results] == [("A", "first")]

    broken = SearxngSearchProvider("http://s", client(lambda _: httpx.Response(502), "http://s"))
    with pytest.raises(JarvisError):
        await broken.search("q")


# ------------------------------------------------------------ documents


def test_chunk_text_packs_and_splits() -> None:
    assert chunk_text("") == []
    assert chunk_text("a\n\nb", size=10, overlap=2) == ["a\n\nb"]
    assert chunk_text("aaaa\n\nbbbb", size=6, overlap=2) == ["aaaa", "bbbb"]
    long = "x" * 25
    assert chunk_text(long, size=10, overlap=3) == ["x" * 10, "x" * 10, "x" * 10, "x" * 4]
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("x", size=5, overlap=5)


async def test_folder_index_refreshes_incrementally(tmp_path: Path) -> None:
    (tmp_path / "travel.md").write_text("My passport expires in March 2027.", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "food.txt").write_text("Favourite dish is adobo.", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    embedder = FakeEmbedder()
    index = FolderDocumentIndex(
        tmp_path, SqliteDocumentChunkStore(Database(":memory:")), embedder, min_score=0.2
    )

    assert await index.refresh() == 2
    assert await index.refresh() == 0  # nothing changed
    hits = await index.search("when does my passport expire")
    assert hits[0].path == "travel.md"

    (tmp_path / "sub" / "food.txt").unlink()
    await index.refresh()
    assert all(hit.path != str(Path("sub") / "food.txt") for hit in await index.search("adobo"))


async def test_folder_index_missing_folder(tmp_path: Path) -> None:
    index = FolderDocumentIndex(
        tmp_path / "missing", SqliteDocumentChunkStore(Database(":memory:")), FakeEmbedder()
    )
    assert await index.refresh() == 0
    assert await index.search("anything") == []


# ------------------------------------------------------------------ MCP


class _FakeMcpSession:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        self.calls.append((name, arguments))
        return self.result


async def test_mcp_tool_bridge() -> None:
    ok = SimpleNamespace(content=[SimpleNamespace(text="42 files")], isError=False)
    session = _FakeMcpSession(ok)
    remote = SimpleNamespace(
        name="count-files", description="Count files.", inputSchema={"type": "object"}
    )
    tool = wrap_tool("files", session, remote)
    assert tool.name == "files__count_files"
    assert tool.label == "Using files"
    assert await tool.handler({"path": "/"}) == "42 files"
    assert session.calls == [("count-files", {"path": "/"})]

    failing = SimpleNamespace(content=[SimpleNamespace(text="denied")], isError=True)
    with pytest.raises(ToolError, match="denied"):
        result_text(failing)
    assert result_text(SimpleNamespace(content=[], isError=False)) == "The tool returned no text."
    assert tool_name("my server", "do.it") == "my_server__do_it"


async def test_mcp_toolset_without_servers() -> None:
    toolset = McpToolset([])
    assert await toolset.start() == []
    await toolset.aclose()
