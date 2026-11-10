"""File-backed storage of the enrolled user's voiceprint."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path


class FileVoiceprintStore:
    """Implements :class:`~jarvis_core.domain.ports.VoiceprintStore` as a JSON file.

    The voiceprint is a speaker embedding, not a recording: it cannot be turned
    back into audio. It is still personal data, so it lives only in the local
    data directory.

    Args:
        path: Where to keep the file, e.g. ``~/.jarvis-os/voiceprint.json``.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[float] | None:
        """Return the stored voiceprint, if any."""
        if not self._path.is_file():
            return None
        data = json.loads(self._path.read_text(encoding="utf-8"))
        vector = data.get("embedding")
        return [float(x) for x in vector] if isinstance(vector, list) and vector else None

    def save(self, voiceprint: Sequence[float]) -> None:
        """Replace the stored voiceprint."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "embedding": [round(float(x), 6) for x in voiceprint]}
        self._path.write_text(json.dumps(payload), encoding="utf-8")

    def clear(self) -> None:
        """Delete the stored voiceprint."""
        self._path.unlink(missing_ok=True)
