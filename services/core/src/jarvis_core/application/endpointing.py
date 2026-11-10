"""Decide when the user has started and finished speaking ("endpointing").

Time is measured in *audio* time (frames received), not wall-clock time. That
keeps the logic deterministic and trivially testable.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from jarvis_core.domain.models import AudioClip
from jarvis_core.domain.ports import VoiceActivityDetector


@dataclass(frozen=True, slots=True)
class UtteranceComplete:
    """The user finished speaking; ``audio`` holds the whole utterance."""

    audio: AudioClip


@dataclass(frozen=True, slots=True)
class ListeningTimedOut:
    """No speech started before the listening window closed."""


EndpointEvent = UtteranceComplete | ListeningTimedOut


@dataclass(frozen=True, slots=True)
class EndpointingConfig:
    """Tuning knobs for :class:`UtteranceRecorder` (all in milliseconds).

    Attributes:
        frame_ms: Duration of each incoming frame.
        end_of_speech_ms: Trailing silence that ends an utterance.
        max_utterance_ms: Hard cap on utterance length.
        pre_roll_ms: Audio kept from *before* speech was detected, so the
            first syllable isn't clipped.
        min_speech_ms: Bursts shorter than this are treated as noise.
    """

    frame_ms: int = 80
    end_of_speech_ms: int = 800
    max_utterance_ms: int = 15_000
    pre_roll_ms: int = 320
    min_speech_ms: int = 240


class UtteranceRecorder:
    """Buffers audio frames and reports when an utterance is complete.

    Args:
        vad: Speech/non-speech classifier.
        sample_rate: Sample rate of incoming frames.
        config: Timing configuration.
    """

    def __init__(
        self,
        vad: VoiceActivityDetector,
        sample_rate: int,
        config: EndpointingConfig | None = None,
    ) -> None:
        self._vad = vad
        self._sample_rate = sample_rate
        self._config = config or EndpointingConfig()
        self._pre_roll: deque[bytes] = deque(
            maxlen=max(1, self._config.pre_roll_ms // self._config.frame_ms)
        )
        self._frames: list[bytes] = []
        self._timeout_ms = 0
        self._waited_ms = 0
        self._speech_ms = 0
        self._silence_ms = 0

    @property
    def speech_started(self) -> bool:
        """Whether the user has begun speaking in the current window."""
        return bool(self._frames)

    def reset(self, timeout_ms: int) -> None:
        """Start a fresh listening window.

        Args:
            timeout_ms: How long to wait for speech to begin.
        """
        self._pre_roll.clear()
        self._frames = []
        self._timeout_ms = timeout_ms
        self._waited_ms = 0
        self._speech_ms = 0
        self._silence_ms = 0

    def push(self, frame: bytes) -> EndpointEvent | None:
        """Feed one frame; return an event when the window is resolved."""
        cfg = self._config
        is_speech = self._vad.is_speech(frame)

        if not self.speech_started:
            self._waited_ms += cfg.frame_ms
            if is_speech:
                self._frames = [*self._pre_roll, frame]
                self._speech_ms = cfg.frame_ms
                self._silence_ms = 0
                return None
            self._pre_roll.append(frame)
            return ListeningTimedOut() if self._waited_ms >= self._timeout_ms else None

        self._frames.append(frame)
        if is_speech:
            self._speech_ms += cfg.frame_ms
            self._silence_ms = 0
        else:
            self._silence_ms += cfg.frame_ms

        utterance_ms = len(self._frames) * cfg.frame_ms
        if self._silence_ms >= cfg.end_of_speech_ms or utterance_ms >= cfg.max_utterance_ms:
            if self._speech_ms < cfg.min_speech_ms:
                # A cough or a click: discard it and keep waiting.
                self._frames = []
                self._speech_ms = 0
                self._silence_ms = 0
                return ListeningTimedOut() if self._waited_ms >= self._timeout_ms else None
            return UtteranceComplete(AudioClip(b"".join(self._frames), self._sample_rate))
        return None
