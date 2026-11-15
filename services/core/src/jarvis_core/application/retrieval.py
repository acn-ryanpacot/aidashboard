"""Hybrid retrieval for the documents folder: meaning *and* keywords.

Embeddings find passages that mean the same as the question ("where did I
work before?" → the employment history in a resume), but they are weak at
exact strings: policy and account numbers, rare surnames, product codes. A
keyword index (Okapi BM25) is the opposite. :func:`fuse` combines both
rankings with reciprocal rank fusion, the standard way to merge rankings
whose scores aren't comparable, and adds a bonus for passages from a file
whose name the question mentions ("my resume" → ``resume.pdf``).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

#: Words that carry no meaning for search.
STOPWORDS = frozenset(
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
        "i",
        "im",
        "much",
        "many",
        "any",
        "some",
        "there",
        "their",
        "our",
        "us",
        "we",
        "have",
        "has",
        "had",
        "get",
        "got",
        "show",
        "give",
        "know",
        "whats",
    ]
)
_WORD = re.compile(r"\w+")
#: Reciprocal-rank-fusion damping constant (60 in the original paper).
RRF_K = 60
#: A passage from a file named in the question gets this much extra fused score
#: (about the value of a first place in one of the two rankings).
NAME_BONUS = 1 / (RRF_K + 1)

#: Task prefixes that some embedding models expect (``(query, document)``).
_PREFIXES: Mapping[str, tuple[str, str]] = {
    "nomic-embed-text": ("search_query: ", "search_document: "),
    "mxbai-embed-large": ("Represent this sentence for searching relevant passages: ", ""),
    "snowflake-arctic-embed": ("Represent this sentence for searching relevant passages: ", ""),
}


def embedding_prefixes(model: str) -> tuple[str, str]:
    """``(query_prefix, document_prefix)`` recommended for an Ollama embedding model.

    ``nomic-embed-text`` is trained with ``search_query:`` / ``search_document:``
    and retrieves noticeably better with them; unknown models get none.
    """
    name = model.lower().split(":", 1)[0].rsplit("/", 1)[-1]
    return _PREFIXES.get(name, ("", ""))


def tokenize(text: str) -> list[str]:
    """Lowercase search terms of ``text``, stopwords removed, plurals folded (bills → bill)."""
    terms = []
    for word in _WORD.findall(text.lower()):
        if word in STOPWORDS or (len(word) < 2 and not word.isdigit()):
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        terms.append(word)
    return terms


class KeywordIndex:
    """Okapi BM25 over a fixed list of passages.

    Args:
        passages: Passage texts; results refer to their positions.
        k1: Term-frequency saturation.
        b: Length normalisation.
    """

    def __init__(self, passages: Sequence[str], *, k1: float = 1.4, b: float = 0.75) -> None:
        self._terms = [Counter(tokenize(text)) for text in passages]
        self._lengths = [sum(terms.values()) for terms in self._terms]
        self._average = (sum(self._lengths) / len(self._lengths)) if self._lengths else 0.0
        self._frequency: Counter[str] = Counter()
        for terms in self._terms:
            self._frequency.update(terms.keys())
        self._k1, self._b = k1, b

    def __len__(self) -> int:
        return len(self._terms)

    def idf(self, term: str) -> float:
        """Inverse document frequency (always positive)."""
        n, df = len(self._terms), self._frequency.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, limit: int = 20) -> list[tuple[int, float]]:
        """``(position, score)`` of the best keyword matches, best first.

        A passage only counts if it contains a *distinctive* query term: one
        found in at most a quarter of the passages (in a collection of eight
        or more). Otherwise a question would match every passage that
        happens to say "payment".
        """
        wanted = set(tokenize(query))
        if not wanted or not self._terms:
            return []
        n = len(self._terms)
        distinctive = {t for t in wanted if n < 8 or self._frequency.get(t, 0) <= n / 4}
        scores = []
        for position, terms in enumerate(self._terms):
            if not distinctive & terms.keys():
                continue
            norm = self._k1 * (1 - self._b + self._b * self._lengths[position] / self._average)
            score = sum(
                self.idf(t) * terms[t] * (self._k1 + 1) / (terms[t] + norm)
                for t in wanted
                if t in terms
            )
            scores.append((position, score))
        scores.sort(key=lambda item: (-item[1], item[0]))
        return scores[:limit]


@dataclass(frozen=True, slots=True)
class Ranked:
    """A passage position with its fused score."""

    position: int
    score: float


def fuse(
    semantic: Sequence[int],
    keyword: Sequence[int],
    *,
    bonus: Iterable[int] = (),
    limit: int = 4,
) -> list[Ranked]:
    """Merge two best-first rankings of passage positions (reciprocal rank fusion).

    Args:
        semantic: Positions ranked by embedding similarity.
        keyword: Positions ranked by BM25.
        bonus: Positions from a file the question names.
        limit: How many to return.
    """
    scores: dict[int, float] = {}
    for ranking in (semantic, keyword):
        for rank, position in enumerate(ranking, start=1):
            scores[position] = scores.get(position, 0.0) + 1 / (RRF_K + rank)
    for position in bonus:
        if position in scores:
            scores[position] += NAME_BONUS
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [Ranked(position, score) for position, score in ranked[:limit]]


def names_in_query(query: str, names: Iterable[str]) -> set[str]:
    """File names whose words the question uses: "my resume" → ``{"cv/resume.pdf"}``.

    Only the file's own name counts (not its folder or extension), and every
    distinctive word of a short name, or two words of a longer one, must appear.
    """
    wanted = set(tokenize(query))
    found = set()
    for name in names:
        stem = name.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        words = {w for w in tokenize(stem.replace("_", " ").replace("-", " ")) if not w.isdigit()}
        if not words:
            continue
        overlap = len(words & wanted)
        if overlap == len(words) or overlap >= 2:
            found.add(name)
    return found
