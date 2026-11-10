"""Split documents into passages small enough to embed and quote."""

from __future__ import annotations

import re

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def chunk_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    """Pack paragraphs into chunks of at most ``size`` characters.

    Paragraphs are kept whole where possible. A paragraph longer than
    ``size`` is cut into windows that overlap by ``overlap`` characters so
    no sentence is lost at a boundary.

    Args:
        text: Document text.
        size: Maximum chunk length.
        overlap: Overlap between windows of an over-long paragraph.

    Returns:
        Chunks in document order (empty for blank input).
    """
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    chunks: list[str] = []
    current = ""
    for paragraph in (p.strip() for p in _PARAGRAPH_BREAK.split(text)):
        if not paragraph:
            continue
        if len(paragraph) > size:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            while start < len(paragraph):
                chunks.append(paragraph[start : start + size])
                if start + size >= len(paragraph):
                    break
                start += size - overlap
            continue
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > size:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
