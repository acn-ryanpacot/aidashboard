"""Turn model output into text that sounds right when read aloud."""

from __future__ import annotations

import re

_CODE_FENCE = re.compile(r"```.*?(```|$)", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_EMPHASIS = re.compile(r"(\*\*|__|\*|_|~~)(?=\S)(.+?)(?<=\S)\1")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_LIST_MARKER = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+", re.MULTILINE)
_WHITESPACE = re.compile(r"\s+")


def to_speakable(text: str) -> str:
    """Strip Markdown and other visual-only syntax so TTS doesn't read it out.

    Args:
        text: Raw text from the language model.

    Returns:
        Plain prose, or an empty string if nothing pronounceable remains.

    Example:
        >>> to_speakable("**Sure!** See [the docs](https://x.io).")
        'Sure! See the docs.'
    """
    text = _CODE_FENCE.sub(" ", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _URL.sub("the link", text)
    text = _EMPHASIS.sub(r"\2", text)
    text = _HEADING.sub("", text)
    text = _LIST_MARKER.sub("", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text if any(ch.isalnum() for ch in text) else ""
