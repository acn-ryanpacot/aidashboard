"""Behaviour of the voice session state machine, end to end, with fakes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from jarvis_core.application.brain import Brain
from jarvis_core.application.conversation import ConversationHistory
from jarvis_core.application.endpointing import EndpointingConfig, UtteranceRecorder
from jarvis_core.application.greeting import GreetingCache
from jarvis_core.application.persona import Persona
from jarvis_core.application.speaker import SpeakerVerification
from jarvis_core.application.tools import builtin
from jarvis_core.application.tools.registry import ToolRegistry
from jarvis_core.application.voice_session import BargeInMode, SessionConfig, VoiceSession
from jarvis_core.domain.events import (
    EnrollmentProgress,
    EnrollmentStatus,
    ErrorOccurred,
    Interrupted,
    Notification,
    SegmentKind,
    SpeakerRejected,
    SpeechSegmentReady,
    StateChanged,
    ToolInvoked,
    TranscriptReady,
    TurnCompleted,
    TurnMetrics,
    WakeDetected,
)
from jarvis_core.domain.models import AssistantState, Role, ToolCall
from tests.fakes import (
    SILENCE,
    SPEECH,
    STRANGER,
    WAKE,
    FakeLlm,
    FakeSpeakerEncoder,
    FakeStt,
    FakeTts,
    FakeVad,
    FakeWake,
    MemoryVoiceprintStore,
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
        with_tts: bool = True,
        with_stt: bool = True,
        follow_up_ms: int = 0,
        barge_in: BargeInMode = "wake_word",
        tools: ToolRegistry | None = None,
        speaker: SpeakerVerification | None = None,
        playback_grace_ms: int = 4_000,
    ) -> None:
        self.sink = RecordingSink()
        self.llm = llm or FakeLlm(LONG_REPLY)
        self.tts = (tts or FakeTts()) if with_tts else None
        self.stt = FakeStt() if with_stt else None
        self.wake = FakeWake()
        persona = Persona("Jarvis", "Ryan", GREETING)
        recorder = UtteranceRecorder(
            FakeVad(),
            16_000,
            EndpointingConfig(frame_ms=80, end_of_speech_ms=240, min_speech_ms=80, pre_roll_ms=160),
        )
        self.session = VoiceSession(
            sink=self.sink,
            brain=Brain(self.llm, persona, tools),
            greeting=GreetingCache(GREETING, self.tts),
            recorder=recorder,
            history=ConversationHistory(10),
            stt=self.stt,
            tts=self.tts,
            wake=self.wake,
            speaker=speaker,
            config=SessionConfig(
                listen_timeout_ms=800,
                follow_up_ms=follow_up_ms,
                barge_in=barge_in,
                barge_in_min_speech_ms=240,
                playback_grace_ms=playback_grace_ms,
            ),
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

    async def speak(self, frame: bytes = SPEECH, frames: int = 3, silence: int = 4) -> None:
        for _ in range(frames):
            await self.session.handle_audio(frame)
        for _ in range(silence):
            await self.session.handle_audio(SILENCE)

    async def finish_playback(self) -> None:
        for segment in self.segments:
            if segment.kind is not SegmentKind.GREETING:
                await self.session.handle_playback_ended(segment.segment_id)


async def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


# ------------------------------------------------------------- core loop


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
    await h.speak(frames=2, silence=3)
    await wait_until(lambda: bool(h.sink.of_type(TurnCompleted)))
    assert h.stt is not None
    [clip] = h.stt.calls
    assert clip.pcm16.startswith(SILENCE)
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
    h.llm.gate = asyncio.Event()
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


async def test_without_stt_activation_does_not_listen() -> None:
    h = Harness(with_stt=False)
    await h.wake_up()
    assert h.state() is AssistantState.IDLE


# ------------------------------------------------------------- phase 2


async def _speaking(h: Harness) -> None:
    await h.session.handle_text_query("tell me something")
    await wait_until(lambda: bool([s for s in h.segments if s.kind is SegmentKind.ANSWER]))
    assert h.state() is AssistantState.SPEAKING


async def test_wake_word_barge_in_interrupts_and_listens() -> None:
    h = Harness()
    await _speaking(h)
    await h.session.handle_audio(WAKE)
    assert h.sink.of_type(Interrupted)
    assert h.state() is AssistantState.LISTENING
    # Late acknowledgements for the interrupted answer are ignored.
    await h.finish_playback()
    assert h.state() is AssistantState.LISTENING


async def test_barge_in_while_thinking() -> None:
    h = Harness()
    h.llm.gate = asyncio.Event()
    await h.session.handle_text_query("slow question")
    await wait_until(lambda: bool(h.llm.requests))
    await h.session.handle_audio(WAKE)
    assert h.state() is AssistantState.LISTENING
    assert h.sink.of_type(TurnCompleted) == []


async def test_client_signalled_voice_barge_in() -> None:
    h = Harness(barge_in="voice")
    await _speaking(h)
    # Raw speech while Jarvis talks is NOT enough on its own (it may be echo)…
    for _ in range(6):
        await h.session.handle_audio(SPEECH)
    assert h.state() is AssistantState.SPEAKING
    # …the client's echo-aware detector decides, then streams the buffered words.
    await h.session.handle_barge_in()
    assert h.state() is AssistantState.LISTENING
    assert h.sink.of_type(Interrupted)
    await h.speak()
    await wait_until(lambda: len(h.sink.of_type(TranscriptReady)) == 2)


async def test_client_barge_in_ignored_unless_voice_mode() -> None:
    h = Harness(barge_in="wake_word")
    await _speaking(h)
    await h.session.handle_barge_in()
    assert h.state() is AssistantState.SPEAKING


async def test_wake_word_still_interrupts_in_voice_mode() -> None:
    h = Harness(barge_in="voice")
    await _speaking(h)
    await h.session.handle_audio(WAKE)
    assert h.state() is AssistantState.LISTENING


async def test_apply_config_changes_behaviour_live() -> None:
    h = Harness(follow_up_ms=0)
    h.session.apply_config(SessionConfig(listen_timeout_ms=800, follow_up_ms=3_000))
    await h.session.handle_text_query("hello")
    await wait_until(lambda: bool(h.sink.of_type(TurnCompleted)))
    await h.finish_playback()
    assert h.state() is AssistantState.LISTENING  # follow-up mode now on


async def test_barge_in_off_ignores_wake_word_while_speaking() -> None:
    h = Harness(barge_in="off")
    await _speaking(h)
    await h.session.handle_audio(WAKE)
    assert h.state() is AssistantState.SPEAKING
    assert h.sink.of_type(Interrupted) == []


async def test_push_to_talk_listens_without_greeting() -> None:
    h = Harness()
    await h.session.listen()
    assert h.state() is AssistantState.LISTENING
    assert h.segments == []
    assert h.sink.of_type(WakeDetected) == []


async def test_playback_watchdog_finishes_unacknowledged_turn() -> None:
    h = Harness(playback_grace_ms=50)
    await h.session.handle_text_query("hello")
    await wait_until(lambda: bool(h.sink.of_type(TurnCompleted)))
    assert h.state() is AssistantState.SPEAKING
    # Two 0.1 s segments back-to-back + 50 ms grace ≈ 0.25 s; never acknowledged.
    await wait_until(lambda: h.state() is AssistantState.IDLE, timeout=2.0)


async def test_metrics_for_spoken_and_typed_turns() -> None:
    h = Harness()
    await h.wake_up()
    await h.speak()
    await wait_until(lambda: bool(h.sink.of_type(TurnMetrics)))
    spoken = h.sink.of_type(TurnMetrics)[0]
    assert spoken.stt_ms is not None and spoken.stt_ms >= 0
    assert spoken.first_token_ms is not None
    assert spoken.first_audio_ms is not None
    assert spoken.total_ms >= spoken.first_token_ms

    await h.finish_playback()
    await h.session.handle_text_query("typed")
    await wait_until(lambda: len(h.sink.of_type(TurnMetrics)) == 2)
    assert h.sink.of_type(TurnMetrics)[1].stt_ms is None


async def test_tool_use_is_reported() -> None:
    llm = FakeLlm(rounds=[[ToolCall("get_current_time", {})], ["It is noon, sir."]])
    tools = ToolRegistry()
    tools.extend(builtin.time_tools())
    h = Harness(llm=llm, tools=tools)
    await h.session.handle_text_query("what time is it")
    await wait_until(lambda: bool(h.sink.of_type(TurnMetrics)))
    [tool] = h.sink.of_type(ToolInvoked)
    assert (tool.name, tool.label) == ("get_current_time", "Checking the time")
    assert h.sink.of_type(TurnMetrics)[0].tools == ("get_current_time",)
    assert h.sink.of_type(TurnCompleted)[0].text == "It is noon, sir."


# ------------------------------------------------------------- voice ID


def _speaker(
    voiceprint: list[float] | None = None,
) -> tuple[SpeakerVerification, MemoryVoiceprintStore]:
    store = MemoryVoiceprintStore(voiceprint)
    return SpeakerVerification(
        FakeSpeakerEncoder(), store, threshold=0.5, samples_required=2
    ), store


async def test_stranger_is_rejected_when_enrolled() -> None:
    speaker, _ = _speaker([1.0, 0.0])
    h = Harness(speaker=speaker)
    await h.wake_up()
    await h.speak(frame=STRANGER)
    await wait_until(lambda: bool(h.sink.of_type(SpeakerRejected)))
    assert h.sink.of_type(TranscriptReady) == []
    assert h.state() is AssistantState.IDLE


async def test_enrolled_user_is_accepted() -> None:
    speaker, _ = _speaker([1.0, 0.0])
    h = Harness(speaker=speaker)
    await h.wake_up()
    await h.speak(frame=SPEECH)
    await wait_until(lambda: bool(h.sink.of_type(TurnCompleted)))
    assert h.sink.of_type(SpeakerRejected) == []


async def test_enrollment_collects_samples_and_saves_voiceprint() -> None:
    speaker, store = _speaker()
    h = Harness(speaker=speaker)
    await h.session.start_enrollment()
    assert h.state() is AssistantState.LISTENING
    await h.speak()
    await h.speak()
    statuses = [(e.status, e.collected) for e in h.sink.of_type(EnrollmentProgress)]
    assert statuses == [
        (EnrollmentStatus.RECORDING, 0),
        (EnrollmentStatus.RECORDING, 1),
        (EnrollmentStatus.COMPLETE, 2),
    ]
    assert store.voiceprint is not None and speaker.enrolled
    assert h.state() is AssistantState.IDLE
    assert h.llm.requests == []  # enrollment never reaches the brain


async def test_enrollment_can_be_cancelled() -> None:
    speaker, store = _speaker()
    h = Harness(speaker=speaker)
    await h.session.start_enrollment()
    await h.session.cancel()
    assert h.sink.of_type(EnrollmentProgress)[-1].status is EnrollmentStatus.CANCELLED
    assert store.voiceprint is None


async def test_enrollment_without_voice_id_reports_error() -> None:
    h = Harness()
    await h.session.start_enrollment()
    assert "Voice ID" in h.sink.of_type(ErrorOccurred)[0].message


# --------------------------------------------------------- announcements


async def test_announcement_spoken_when_idle_then_back_to_idle() -> None:
    h = Harness(follow_up_ms=2_000)
    await h.session.announce("reminder", "Call the dentist")
    assert h.sink.of_type(Notification)[0].text == "Call the dentist"
    [segment] = h.segments
    assert segment.kind is SegmentKind.ANNOUNCEMENT
    await h.session.handle_playback_ended(segment.segment_id)
    assert h.state() is AssistantState.IDLE  # no follow-up listening after a reminder


async def test_announcement_waits_until_idle() -> None:
    h = Harness()
    await _speaking(h)
    await h.session.announce("reminder", "Stand up and stretch")
    assert all(s.kind is not SegmentKind.ANNOUNCEMENT for s in h.segments)
    await wait_until(lambda: bool(h.sink.of_type(TurnCompleted)))
    await h.finish_playback()
    await wait_until(lambda: any(s.kind is SegmentKind.ANNOUNCEMENT for s in h.segments))
