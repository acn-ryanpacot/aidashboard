from __future__ import annotations

from jarvis_core.application.endpointing import (
    EndpointingConfig,
    ListeningTimedOut,
    UtteranceComplete,
    UtteranceRecorder,
)
from tests.fakes import SILENCE, SPEECH, FakeVad

CONFIG = EndpointingConfig(
    frame_ms=80, end_of_speech_ms=240, max_utterance_ms=800, pre_roll_ms=160, min_speech_ms=160
)


def make(timeout_ms: int = 800) -> UtteranceRecorder:
    recorder = UtteranceRecorder(FakeVad(), 16_000, CONFIG)
    recorder.reset(timeout_ms)
    return recorder


def test_utterance_completes_after_trailing_silence() -> None:
    recorder = make()
    events = [recorder.push(f) for f in [SILENCE, SPEECH, SPEECH, SILENCE, SILENCE, SILENCE]]
    assert events[:-1] == [None] * 5
    final = events[-1]
    assert isinstance(final, UtteranceComplete)
    # pre-roll (1 silence) + 2 speech + 3 trailing silence
    assert final.audio.pcm16 == SILENCE + SPEECH * 2 + SILENCE * 3
    assert final.audio.sample_rate == 16_000


def test_times_out_when_nobody_speaks() -> None:
    recorder = make(timeout_ms=240)
    assert recorder.push(SILENCE) is None
    assert recorder.push(SILENCE) is None
    assert isinstance(recorder.push(SILENCE), ListeningTimedOut)


def test_short_noise_burst_is_ignored() -> None:
    recorder = make()
    for frame in [SPEECH, SILENCE, SILENCE, SILENCE]:
        assert recorder.push(frame) is None
    assert not recorder.speech_started


def test_max_utterance_length_forces_completion() -> None:
    recorder = make()
    events = [recorder.push(SPEECH) for _ in range(10)]
    assert isinstance(events[9], UtteranceComplete)
    assert all(e is None for e in events[:9])


def test_reset_starts_a_fresh_window() -> None:
    recorder = make()
    recorder.push(SPEECH)
    recorder.reset(800)
    assert not recorder.speech_started
