"""Behaviour of the voice session state machine, end to end, with fakes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from jarvis_core.application.conversation import ConversationHistory
from jarvis_core.application.endpointing import EndpointingConfig, UtteranceRecorder
from jarvis_core.application.greeting import GreetingCache
from jarvis_core.application.persona import Persona
from jarvis_core.application.voice_session import SessionConfig, VoiceSession
from jarvis_core.domain.events import (
    ErrorOccurred,
    SegmentKind,
    SpeechSegmentReady,
    StateChanged,
    TranscriptReady,
    TurnCompleted,
    WakeDetected,
)
from jarvis_core.domain.models import AssistantState, Role
from tests.fakes import (
    SILENCE,
    SPEECH,
    WAKE,
    FakeLlm,
    FakeStt,
    FakeTts,
    FakeVad,
    FakeWake,
    RecordingSink,
)

GREETING = "How can I help you Ryan?"
LONG_REPLY = ("The time is twelve o'clock. ", "Your next meeting starts in an hour.")


class Harness:
    def __init__(
        self,
        *,
        llm: FakeLlm | None = None,
        tts: FakeTts | None = None,
        stt: FakeStt | None = None,
        with_tts: bool = True,
        with_stt: bool = True,
        follow_up_ms: int = 0,
    ) -> None:
        self.sink = RecordingSink()
        self.llm = llm or FakeLlm(LONG_REPLY)
        self.tts = (tts or FakeTts()) if with_tts else None
        self.stt = (stt or FakeStt()) if with_stt else None
        self.wake = FakeWake()
        recorder = UtteranceRecorder(
            FakeVad(),
            16_000,
            EndpointingConfig(frame_ms=80, end_of_speech_ms=240, min_speech_ms=80, pre_roll_ms=160),
        )
        self.session = VoiceSession(
            sink=self.sink,
            persona=Persona("Jarvis", "Ryan", GREETING),
            greeting=GreetingCache(GREETING, self.tts),
            llm=self.llm,
            recorder=recorder,
            history=ConversationHistory(10),
            stt=self.stt,
            tts=self.tts,
            wake=self.wake,
            config=SessionConfig(listen_timeout_ms=800, follow_up_ms=follow_up_ms),
        )

    def state(self) -> AssistantState:
        return self.session.state

    @property
    def states(self) -> list[AssistantState]:
        return [e.state for e in self.sink.of_type(StateChanged)]

    @property
    def segments(self) -> list[SpeechSegmentReady]:
        return self.sink.of_type(SpeechSegmentReady)

    async def wake_up(self) -> None:
        await self.session.handle_audio(WAKE)
        await self.session.handle_playback_ended(self.segments[-1].segment_id)

    async def speak(self, speech_frames: int = 3, silence_frames: int = 4) -> None:
        for _ in range(speech_frames):
            await self.session.handle_audio(SPEECH)
        for _ in range(silence_frames):
            await self.session.handle_audio(SILENCE)

    async def finish_playback(self) -> None:
        for segment in self.segments:
            if segment.kind is SegmentKind.ANSWER:
                await self.session.handle_playback_ended(segment.segment_id)


async def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


async def test_wake_word_plays_fixed_greeting_without_llm() -> None:
    h = Harness()
    await h.session.handle_audio(SILENCE)
    assert h.sink.events == []

    await h.session.handle_audio(WAKE)

    assert h.sink.of_type(WakeDetected)
    [greeting] = h.segments
    assert greeting.kind is SegmentKind.GREETING
    assert greeting.speech.text == GREETING
    assert h.state() is AssistantState.SPEAKING
    assert h.llm.requests == []
    assert h.wake.resets >= 1


async def test_greeting_is_synthesised_once_and_cached() -> None:
    h = Harness()
    for _ in range(2):
        await h.session.activate()
    assert h.tts is not None
    assert h.tts.spoken.count(GREETING) == 1


async def test_full_spoken_turn_returns_to_idle() -> None:
    h = Harness()
    await h.wake_up()
    assert h.state() is AssistantState.LISTENING

    await h.speak()
    await wait_until(lambda: bool(h.sink.of_type(TurnCompleted)))

    assert h.sink.of_type(TranscriptReady)[0].text == "what time is it"
    answers = [s for s in h.segments if s.kind is SegmentKind.ANSWER]
    assert [s.speech.text for s in answers] == [
        "The time is twelve o'clock.",
        "Your next meeting starts in an hour.",
    ]
    assert h.state() is AssistantState.SPEAKING

    await h.finish_playback()
    assert h.state() is AssistantState.IDLE
    assert h.states == [
        AssistantState.SPEAKING,
        AssistantState.LISTENING,
        AssistantState.THINKING,
        AssistantState.SPEAKING,
        AssistantState.IDLE,
    ]


async def test_recorded_utterance_includes_pre_roll() -> None:
    h = Harness()
    await h.wake_up()
    await h.session.handle_audio(SILENCE)
    await h.session.handle_audio(SILENCE)
    await h.speak(speech_frames=2, silence_frames=3)
    await wait_until(lambda: bool(h.sink.of_type(TurnCompleted)))

    assert h.stt is not None
    [clip] = h.stt.calls
    assert clip.pcm16.startswith(SILENCE)  # pre-roll kept the lead-in
    assert SPEECH in clip.pcm16


async def test_listening_times_out_to_idle() -> None:
    h = Harness()
    await h.wake_up()
    for _ in range(10):
        await h.session.handle_audio(SILENCE)
    assert h.state() is AssistantState.IDLE
    assert h.llm.requests == []


async def test_follow_up_mode_keeps_listening_after_answer() -> None:
    h = Harness(follow_up_ms=2_000)
    await h.session.handle_text_query("hello")
    await wait_until(lambda: bool(h.sink.of_type(TurnCompleted)))
    await h.finish_playback()
    assert h.state() is AssistantState.LISTENING


async def test_text_query_skips_stt_and_builds_history() -> None:
    h = Harness()
    await h.session.handle_text_query("first question")
    await wait_until(lambda: len(h.sink.of_type(TurnCompleted)) == 1)
    await h.finish_playback()
    await h.session.handle_text_query("second question")
    await wait_until(lambda: len(h.sink.of_type(TurnCompleted)) == 2)

    assert h.stt is not None and h.stt.calls == []
    second_request = h.llm.requests[1]
    assert second_request[0].role is Role.SYSTEM
    assert [m.content for m in second_request[1:]] == [
        "first question",
        "".join(LONG_REPLY).strip(),
        "second question",
    ]


async def test_markdown_is_stripped_before_speaking() -> None:
    h = Harness(llm=FakeLlm(["**Certainly.** Here is a `snippet` for you, sir."]))
    await h.session.handle_text_query("show me")
    await wait_until(lambda: bool(h.sink.of_type(TurnCompleted)))
    assert h.tts is not None
    assert h.tts.spoken == ["Certainly. Here is a snippet for you, sir."]


async def test_llm_failure_reports_error_and_goes_idle() -> None:
    h = Harness()
    h.llm.fail = True
    await h.session.handle_text_query("hello")
    await wait_until(lambda: bool(h.sink.of_type(ErrorOccurred)))
    assert h.sink.of_type(ErrorOccurred)[0].message == "model offline"
    assert h.state() is AssistantState.IDLE


async def test_cancel_stops_generation() -> None:
    h = Harness()
    h.llm.gate = asyncio.Event()  # block the model mid-answer
    await h.session.handle_text_query("tell me a long story")
    await wait_until(lambda: bool(h.llm.requests))

    await h.session.cancel()

    assert h.state() is AssistantState.IDLE
    assert h.sink.of_type(TurnCompleted) == []


async def test_text_only_mode_without_tts() -> None:
    h = Harness(with_tts=False)
    await h.session.activate()
    assert h.sink.of_type(TurnCompleted)[0].text == GREETING
    assert h.state() is AssistantState.LISTENING

    await h.session.handle_text_query("hi")
    await wait_until(lambda: len(h.sink.of_type(TurnCompleted)) == 2)
    await wait_until(lambda: h.state() is AssistantState.IDLE)
    assert h.segments == []


@pytest.mark.parametrize("with_stt", [False])
async def test_without_stt_activation_does_not_listen(with_stt: bool) -> None:
    h = Harness(with_stt=with_stt)
    await h.wake_up()
    assert h.state() is AssistantState.IDLE
