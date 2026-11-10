"""Fallback word timings for TTS engines that don't report them."""

from __future__ import annotations

from jarvis_core.domain.models import WordTiming


def estimate_word_timings(text: str, duration_seconds: float) -> tuple[WordTiming, ...]:
    """Spread words across ``duration_seconds`` in proportion to their length.

    Good enough to drive karaoke-style captions when an engine provides no
    alignment data. Each word is weighted by its character count plus one
    (for the gap after it).

    Args:
        text: The spoken text.
        duration_seconds: Length of the synthesised audio.

    Returns:
        One :class:`WordTiming` per whitespace-separated word.
    """
    words = text.split()
    if not words or duration_seconds <= 0:
        return ()
    total_weight = sum(len(word) + 1 for word in words)
    timings: list[WordTiming] = []
    cursor = 0.0
    for word in words:
        span = duration_seconds * (len(word) + 1) / total_weight
        timings.append(WordTiming(word, round(cursor, 3), round(cursor + span, 3)))
        cursor += span
    return tuple(timings)
