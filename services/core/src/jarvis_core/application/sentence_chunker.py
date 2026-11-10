"""Split a streamed LLM answer into sentences as soon as each one is complete.

Speaking sentence-by-sentence is what makes Jarvis feel responsive: the first
sentence is synthesised and playing while the model is still writing the rest.
"""

from __future__ import annotations

import re

# A sentence ends at terminal punctuation (optionally followed by closing quotes
# or brackets) and whitespace, or at a line break. Requiring trailing
# whitespace keeps decimals ("3.5") and URLs intact while streaming.
_BOUNDARY = re.compile(r"(?<=[.!?…])[\"'”’)\]]*\s+|\n+")  # noqa: RUF001 - typographic quotes are intended


class SentenceChunker:
    """Incrementally turns text deltas into complete sentences.

    Very short fragments ("Sure.", "Mr.") are merged with the following
    sentence so the TTS engine always receives natural-sounding phrases.

    Args:
        min_chars: Minimum length of an emitted sentence.

    Example:
        >>> chunker = SentenceChunker(min_chars=5)
        >>> chunker.feed("Hello there. How ar")
        ['Hello there.']
        >>> chunker.feed("e you?")
        []
        >>> chunker.flush()
        'How are you?'
    """

    def __init__(self, min_chars: int = 20) -> None:
        self._min_chars = min_chars
        self._buffer = ""

    def feed(self, delta: str) -> list[str]:
        """Add streamed text; return any sentences that are now complete."""
        self._buffer += delta
        sentences: list[str] = []
        search_from = 0
        while match := _BOUNDARY.search(self._buffer, search_from):
            candidate = self._buffer[: match.end()].strip()
            if len(candidate) >= self._min_chars:
                sentences.append(candidate)
                self._buffer = self._buffer[match.end() :]
                search_from = 0
            else:
                search_from = match.end()
        return sentences

    def flush(self) -> str | None:
        """Return whatever text remains (the final sentence), then reset."""
        remainder = self._buffer.strip()
        self._buffer = ""
        return remainder or None
