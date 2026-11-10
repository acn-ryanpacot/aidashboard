"""Cache for the fixed wake-word greeting ("How can I help you Ryan?")."""

from __future__ import annotations

import asyncio

from jarvis_core.domain.models import SynthesizedSpeech
from jarvis_core.domain.ports import TextToSpeech


class GreetingCache:
    """Synthesises the greeting once and replays it instantly afterwards.

    The greeting never goes through the language model: it is always exactly
    the configured phrase, and serving it from memory keeps the
    wake-to-response latency well under 300 ms.

    Args:
        text: The greeting phrase.
        tts: Speech engine, or ``None`` for text-only operation.
    """

    def __init__(self, text: str, tts: TextToSpeech | None) -> None:
        self.text = text
        self._tts = tts
        self._speech: SynthesizedSpeech | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> SynthesizedSpeech | None:
        """Return the cached greeting audio (synthesising it on first use)."""
        if self._tts is None:
            return None
        if self._speech is None:
            async with self._lock:
                if self._speech is None:
                    self._speech = await asyncio.to_thread(self._tts.synthesize, self.text)
        return self._speech
