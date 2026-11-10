"""Small, dependency-light similarity helpers for semantic search."""

from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np

_WORD = re.compile(r"[a-z0-9']+")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "do",
        "for",
        "from",
        "has",
        "have",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "so",
        "that",
        "the",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
    ]
)


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity in ``[-1, 1]``; ``0.0`` if either vector is empty or zero."""
    if not a or not b or len(a) != len(b):
        return 0.0
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    denominator = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denominator) if denominator else 0.0


def keywords(text: str) -> set[str]:
    """Lower-cased content words of ``text`` (stop-words removed)."""
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 1}


def keyword_overlap(query: str, text: str) -> float:
    """Fraction of the query's keywords that appear in ``text`` (``0…1``).

    The fallback ranking used when no embedding model is available.
    """
    wanted = keywords(query)
    return len(wanted & keywords(text)) / len(wanted) if wanted else 0.0


def mean_vector(vectors: Sequence[Sequence[float]]) -> list[float]:
    """Element-wise mean of equally sized vectors, L2-normalised."""
    if not vectors:
        raise ValueError("at least one vector is required")
    mean = np.mean(np.asarray(vectors, dtype=np.float32), axis=0)
    norm = float(np.linalg.norm(mean))
    return [float(x) for x in (mean / norm if norm else mean)]
