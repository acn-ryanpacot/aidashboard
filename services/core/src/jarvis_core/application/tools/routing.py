"""Per-request tool routing: attach only the tools a request plausibly needs.

On a CPU, prompt processing dominates latency, and every tool description
costs tokens. With all twelve built-in tools attached, a 3B model processes
about 1,000 prompt tokens (~16 s on a laptop CPU) before saying a word; with
the right two or three attached it is ~4 s, and with none ~1 s. Fewer tools
also means fewer spurious tool calls. See ``docs/adr/0011-tool-routing.md``.

Routing is two-stage:

1. **Keywords** (instant, deterministic): each :class:`ToolGroup` has a few
   regular expressions; any match attaches the whole group.
2. **Embeddings** (optional, ~50 ms): if no keyword matched and an embedding
   model is available, the request is compared with each group's description
   and the best match above a threshold is attached.

If the request itself matches nothing, the previous user message is tried
next, so vague follow-ups ("and the other one too") keep the tools of the
conversation they belong to without dragging old topics into new ones.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

import structlog

from jarvis_core.application.vectors import cosine_similarity
from jarvis_core.domain.models import ToolSpec
from jarvis_core.domain.ports import EmbeddingModel

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ToolGroup:
    """Tools that belong together, with the cues that call for them.

    Attributes:
        name: Group id, e.g. ``tasks``.
        description: One sentence used for embedding-based routing.
        tools: Names (or ``prefix*`` patterns) of the tools in the group.
        patterns: Case-insensitive regular expressions that trigger the group.
    """

    name: str
    description: str
    tools: tuple[str, ...]
    patterns: tuple[str, ...] = ()
    _compiled: tuple[re.Pattern[str], ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        compiled = tuple(re.compile(p, re.IGNORECASE) for p in self.patterns)
        object.__setattr__(self, "_compiled", compiled)

    def matches(self, text: str) -> bool:
        """Whether any trigger pattern occurs in ``text``."""
        return any(pattern.search(text) for pattern in self._compiled)

    def owns(self, tool_name: str) -> bool:
        """Whether ``tool_name`` belongs to this group."""
        return any(
            tool_name.startswith(t[:-1]) if t.endswith("*") else tool_name == t for t in self.tools
        )


#: Groups for the built-in tools. Patterns favour recall over precision: an
#: extra group costs ~150 tokens, a missing one costs a wrong answer.
BUILTIN_GROUPS: tuple[ToolGroup, ...] = (
    ToolGroup(
        "time",
        "The current time, date or day of the week.",
        ("get_current_time",),
        (r"\btime\b", r"\bdate\b", r"\bwhat day\b", r"\bo'?clock\b", r"\bwhat year\b"),
    ),
    ToolGroup(
        "tasks",
        "The user's to-do list: adding, listing or completing tasks.",
        ("add_task", "list_tasks", "complete_task"),
        (
            r"\btasks?\b",
            r"\bto-?dos?\b",
            r"\b(my|the|shopping|grocery|groceries) list\b",
            r"\bput\b.*\bon\b.*\blist\b",
            r"\b(mark|tick|cross|check)\b.*\b(done|off|complete[d]?)\b",
            r"\bi (need|have) to\b",
            r"\bdon'?t let me forget\b",
        ),
    ),
    ToolGroup(
        "reminders",
        "Spoken reminders at a later time: setting, listing or cancelling them.",
        ("set_reminder", "list_reminders", "cancel_reminder"),
        (r"\bremind", r"\balarm\b", r"\bnudge me\b", r"\balert me\b", r"\bin \d+ (min|hour)"),
    ),
    ToolGroup(
        "memory",
        "Long-term facts about the user: remembering, recalling or forgetting them.",
        ("remember", "recall", "forget"),
        (
            r"\bremember\b",
            r"\brecall\b",
            r"\bforget\b",
            r"\bdid i (tell|mention)\b",
            r"\bwhat do you know about me\b",
            r"\bkeep in mind\b",
            r"\bnote that\b",
        ),
    ),
    ToolGroup(
        "weather",
        "Current weather, temperature or forecast somewhere.",
        ("get_weather",),
        (
            r"\bweather\b",
            r"\bforecast\b",
            r"\btemperature\b",
            r"\brain(ing|y)?\b",
            r"\bsunny\b",
            r"\bumbrella\b",
            r"\bhumid",
            r"\b(hot|cold|warm) (outside|today)\b",
        ),
    ),
    ToolGroup(
        "encyclopedia",
        "Factual background about people, places, things, events or history.",
        ("lookup_encyclopedia",),
        (
            r"\bwho (is|was|were|invented|discovered|wrote)\b",
            r"\bwikipedia\b",
            r"\bencyclop",
            r"\bhistory of\b",
            r"\btell me about\b",
            r"\bwhen (was|did)\b",
        ),
    ),
    ToolGroup(
        "web",
        "Recent news, current events, prices, scores or anything needing a web search.",
        ("web_search",),
        (
            r"\bnews\b",
            r"\blatest\b",
            r"\bheadlines?\b",
            r"\bsearch\b",
            r"\blook (it )?up\b",
            r"\bgoogle\b",
            r"\bprice of\b",
            r"\bscore\b",
            r"\bthis week\b",
        ),
    ),
    ToolGroup(
        "documents",
        "The user's own notes and documents.",
        ("search_documents",),
        (
            r"\bmy (notes|documents|docs|files|journal)\b",
            r"\bdid i write\b",
            r"\bin my notes\b",
        ),
    ),
)


def mcp_group(server: str, tools: Sequence[ToolSpec]) -> ToolGroup:
    """A routing group for an MCP server: triggered by its name or tool-name words."""
    words = {server.lower()}
    for spec in tools:
        words |= {w for w in re.split(r"[_\W]+", spec.name.lower()) if len(w) > 3}
    words.discard(server.lower() + "_")
    patterns = tuple(rf"\b{re.escape(w)}" for w in sorted(words))
    return ToolGroup(server, f"Tools from the {server} service.", (f"{server}__*",), patterns)


class ToolRouter:
    """Chooses which tools to attach to a request.

    Args:
        groups: Routing groups (built-ins plus any MCP groups).
        embedder: Optional embedding model for the fallback stage.
        max_tools: Upper bound on attached tools.
        min_similarity: Threshold for the embedding fallback.
    """

    def __init__(
        self,
        groups: Sequence[ToolGroup] = BUILTIN_GROUPS,
        embedder: EmbeddingModel | None = None,
        *,
        max_tools: int = 6,
        min_similarity: float = 0.45,
    ) -> None:
        self._groups = list(groups)
        self._embedder = embedder
        self._max_tools = max_tools
        self._min_similarity = min_similarity
        self._group_vectors: dict[str, list[float]] | None = None
        self._embedder_failed = False

    def add_group(self, group: ToolGroup) -> None:
        """Register another group (e.g. for an MCP server started later)."""
        self._groups.append(group)
        self._group_vectors = None

    async def select(
        self, request: str, available: Sequence[ToolSpec], previous: str | None = None
    ) -> list[ToolSpec]:
        """Return the subset of ``available`` worth attaching to ``request``."""
        if not available:
            return []
        chosen = [g for g in self._groups if g.matches(request)]
        stage = "keywords"
        if not chosen and previous:
            chosen = [g for g in self._groups if g.matches(previous)]
            stage = "previous"
        if not chosen:
            chosen = await self._by_embedding(request)
            stage = "embedding"
        selected = [spec for spec in available if any(group.owns(spec.name) for group in chosen)][
            : self._max_tools
        ]
        log.debug(
            "tools_routed",
            stage=stage if selected else "none",
            groups=[g.name for g in chosen],
            tools=[s.name for s in selected],
        )
        return selected

    async def _by_embedding(self, request: str) -> list[ToolGroup]:
        if self._embedder is None or self._embedder_failed:
            return []
        try:
            if self._group_vectors is None:
                vectors = await self._embedder.embed([g.description for g in self._groups])
                self._group_vectors = {
                    g.name: v for g, v in zip(self._groups, vectors, strict=True)
                }
            [query] = await self._embedder.embed([request])
        except Exception as exc:
            self._embedder_failed = True
            log.warning("tool_routing_embedding_unavailable", error=str(exc))
            return []
        scored = sorted(
            ((cosine_similarity(query, self._group_vectors[g.name]), g) for g in self._groups),
            key=lambda pair: pair[0],
            reverse=True,
        )
        best_score, best = scored[0]
        return [best] if best_score >= self._min_similarity else []
