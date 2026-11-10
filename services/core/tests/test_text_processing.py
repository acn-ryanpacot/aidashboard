from __future__ import annotations

import itertools

import pytest

from jarvis_core.adapters.tts.timing import estimate_word_timings
from jarvis_core.application.sentence_chunker import SentenceChunker
from jarvis_core.application.speech_text import to_speakable


class TestSentenceChunker:
    def test_emits_sentences_as_they_complete(self) -> None:
        chunker = SentenceChunker(min_chars=5)
        assert chunker.feed("Good morning, sir. The weath") == ["Good morning, sir."]
        assert chunker.feed("er is fine! Shall I") == ["The weather is fine!"]
        assert chunker.flush() == "Shall I"
        assert chunker.flush() is None

    def test_short_fragments_are_merged(self) -> None:
        chunker = SentenceChunker(min_chars=20)
        assert chunker.feed("Sure. ") == []
        assert chunker.feed("I have set the timer for you. ") == [
            "Sure. I have set the timer for you."
        ]

    def test_decimals_and_urls_are_not_split(self) -> None:
        chunker = SentenceChunker(min_chars=1)
        assert chunker.feed("Pi is 3.14 roughly") == []
        assert chunker.flush() == "Pi is 3.14 roughly"

    def test_newlines_end_sentences(self) -> None:
        chunker = SentenceChunker(min_chars=1)
        assert chunker.feed("First line\nSecond") == ["First line"]

    def test_closing_quotes_stay_with_sentence(self) -> None:
        chunker = SentenceChunker(min_chars=1)
        assert chunker.feed('He said "hello." Then') == ['He said "hello."']


@pytest.mark.parametrize(
    ("raw", "spoken"),
    [
        ("**Bold** and _italic_", "Bold and italic"),
        ("## Heading\n- item one\n- item two", "Heading item one item two"),
        ("Run `ls` now", "Run ls now"),
        ("See [docs](https://example.com)", "See docs"),
        ("Visit https://example.com today", "Visit the link today"),
        ("Code:\n```python\nprint(1)\n```\nDone", "Code: Done"),
        ("***", ""),
    ],
)
def test_to_speakable(raw: str, spoken: str) -> None:
    assert to_speakable(raw) == spoken


def test_estimated_timings_cover_duration_in_order() -> None:
    timings = estimate_word_timings("How can I help you Ryan?", 2.0)
    assert [t.word for t in timings] == ["How", "can", "I", "help", "you", "Ryan?"]
    assert timings[0].start == 0.0
    assert timings[-1].end == pytest.approx(2.0, abs=0.01)
    assert all(a.end <= b.start + 1e-6 for a, b in itertools.pairwise(timings))


def test_estimated_timings_empty_input() -> None:
    assert estimate_word_timings("", 1.0) == ()
    assert estimate_word_timings("hi", 0.0) == ()
