"""The voice session: Jarvis's conversational state machine.

One :class:`VoiceSession` exists per connected client. It consumes microphone
frames and client commands, and publishes :mod:`~jarvis_core.domain.events`
through a :class:`~jarvis_core.domain.ports.VoiceEventSink`.

State diagram::

            wake word / activate()                 listen() (push-to-talk)
    IDLE ─────────────────────────────▶ SPEAKING (greeting)        │
     ▲                                     │ playback_ended        │
     │ timeout                             ▼                       ▼
     ├──────────────────────────────── LISTENING ◀──────────────┬──────┐
     │                                     │ end of speech       │      │
     │                                     ▼   (or text query)   │ follow-up
     │                                 THINKING ── barge-in ─────┤      │
     │                                     │ first sentence      │      │
     │                                     ▼                     │      │
     └──── (follow-up disabled) ────── SPEAKING (answer) ────────┘──────┘
                                        last playback_ended / barge-in

Concurrency model: all public ``handle_*`` methods are called sequentially
from the transport's receive loop. Generating an answer runs in a separate
task (so the loop keeps receiving frames for barge-in, ``playback_ended`` and
``cancel``), and blocking model calls run in worker threads via
:func:`asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import time
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog

from jarvis_core.application.brain import Brain, ToolUse
from jarvis_core.application.conversation import ConversationHistory
from jarvis_core.application.endpointing import (
    ListeningTimedOut,
    UtteranceComplete,
    UtteranceRecorder,
)
from jarvis_core.application.greeting import GreetingCache
from jarvis_core.application.sentence_chunker import SentenceChunker
from jarvis_core.application.speaker import SpeakerVerification
from jarvis_core.application.speech_text import to_speakable
from jarvis_core.domain.errors import JarvisError, LanguageModelError
from jarvis_core.domain.events import (
    AssistantTextDelta,
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
from jarvis_core.domain.models import AssistantState, AudioClip, SynthesizedSpeech, TextDelta
from jarvis_core.domain.ports import (
    SpeechToText,
    TextToSpeech,
    VoiceActivityDetector,
    VoiceEventSink,
    WakeWordDetector,
)

log = structlog.get_logger(__name__)

_GENERIC_ERROR = "I'm afraid something went wrong on my side. Please try again."

BargeInMode = Literal["off", "wake_word", "voice"]


@dataclass(frozen=True, slots=True)
class SessionConfig:
    """Behavioural settings for a :class:`VoiceSession` (milliseconds).

    Attributes:
        listen_timeout_ms: How long to wait for speech after the greeting.
        follow_up_ms: How long to keep listening after an answer without
            requiring the wake word again. ``0`` disables follow-up mode.
        barge_in: How the user can interrupt Jarvis while it thinks or talks:
            ``wake_word`` (say it again), ``voice`` (just start talking — needs
            good echo cancellation) or ``off``.
        barge_in_min_speech_ms: Continuous speech needed for ``voice`` barge-in.
        playback_grace_ms: Extra time allowed for a client to acknowledge a
            speech segment before it is assumed finished.
        frame_ms: Duration of one audio frame.
    """

    listen_timeout_ms: int = 6_000
    follow_up_ms: int = 6_000
    barge_in: BargeInMode = "wake_word"
    barge_in_min_speech_ms: int = 400
    playback_grace_ms: int = 4_000
    frame_ms: int = 80


@dataclass(slots=True)
class _TurnTimer:
    """Collects timestamps for :class:`TurnMetrics`."""

    started: float
    stt_ms: float | None = None
    first_token: float | None = None
    first_audio: float | None = None
    tools: list[str] = field(default_factory=list)


class VoiceSession:
    """Orchestrates wake → greet → listen → think → speak for one client.

    Args:
        sink: Where events are published.
        brain: Answers requests (LLM + tools + memory).
        greeting: Cached wake-word greeting.
        recorder: Endpointing for spoken requests.
        history: Short-term conversation memory.
        stt: Speech recognition, or ``None`` for text-only mode.
        tts: Speech synthesis, or ``None`` for text-only mode.
        wake: Wake-word detector, or ``None`` to rely on manual activation.
        barge_vad: Voice detector used for ``voice`` barge-in.
        speaker: Voice ID, or ``None`` to accept every voice.
        config: Timing behaviour.
        clock: Monotonic clock in seconds (injectable for tests).
    """

    def __init__(
        self,
        *,
        sink: VoiceEventSink,
        brain: Brain,
        greeting: GreetingCache,
        recorder: UtteranceRecorder,
        history: ConversationHistory,
        stt: SpeechToText | None = None,
        tts: TextToSpeech | None = None,
        wake: WakeWordDetector | None = None,
        barge_vad: VoiceActivityDetector | None = None,
        speaker: SpeakerVerification | None = None,
        config: SessionConfig | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._sink = sink
        self._brain = brain
        self._greeting = greeting
        self._recorder = recorder
        self._history = history
        self._stt = stt
        self._tts = tts
        self._wake = wake
        self._barge_vad = barge_vad
        self._speaker = speaker
        self._config = config or SessionConfig()
        self._clock = clock

        self._state = AssistantState.IDLE
        self._turn_task: asyncio.Task[None] | None = None
        self._segment_ids = itertools.count(1)
        self._greeting_segment: str | None = None
        self._pending_segments: set[str] = set()
        self._generation_done = False
        self._follow_up_after = True
        self._watchdogs: dict[str, asyncio.TimerHandle] = {}
        self._playback_deadline = 0.0
        self._barge_frames: list[bytes] = []
        self._enrollment: list[list[float]] | None = None
        self._announcements: deque[tuple[str, str]] = deque(maxlen=10)
        self._background: set[asyncio.Task[Any]] = set()
        self._timer: _TurnTimer | None = None

    # ------------------------------------------------------------ public API

    @property
    def state(self) -> AssistantState:
        """The current assistant state."""
        return self._state

    @property
    def enrolling(self) -> bool:
        """Whether a voice-ID enrollment is in progress."""
        return self._enrollment is not None

    async def start(self) -> None:
        """Announce the initial state to the client."""
        await self._sink.publish(StateChanged(self._state))

    async def handle_audio(self, frame: bytes) -> None:
        """Process one 80 ms microphone frame (16 kHz mono PCM16)."""
        state = self._state
        if state is AssistantState.IDLE:
            if self._wake is not None and self._wake.process(frame):
                log.info("wake_word_detected")
                await self.activate()
        elif state is AssistantState.LISTENING:
            event = self._recorder.push(frame)
            if isinstance(event, UtteranceComplete):
                await self._on_utterance(event.audio)
            elif isinstance(event, ListeningTimedOut):
                log.info("listening_timed_out")
                if self._enrollment is not None:
                    await self._end_enrollment(EnrollmentStatus.CANCELLED)
                else:
                    await self._go_idle()
        elif self._enrollment is None:  # THINKING or SPEAKING
            await self._check_barge_in(frame)

    async def activate(self) -> None:
        """Greet the user and start listening (wake word or manual trigger)."""
        await self._stop_everything()
        if self._wake is not None:
            self._wake.reset()
        await self._sink.publish(WakeDetected())
        speech = await self._greeting.get()
        if speech is None:
            await self._sink.publish(TurnCompleted(self._greeting.text))
            await self._listen(self._config.listen_timeout_ms)
        else:
            await self._emit_speech(speech, SegmentKind.GREETING)

    async def listen(self) -> None:
        """Push-to-talk: skip the greeting and start listening immediately."""
        await self._stop_everything()
        if self._wake is not None:
            self._wake.reset()
        await self._listen(self._config.listen_timeout_ms)

    async def handle_text_query(self, text: str) -> None:
        """Answer a typed question, bypassing wake word and speech recognition."""
        text = text.strip()
        if not text:
            return
        await self._stop_everything()
        await self._start_turn(text=text)

    async def handle_playback_ended(self, segment_id: str) -> None:
        """The client finished playing a speech segment."""
        if handle := self._watchdogs.pop(segment_id, None):
            handle.cancel()
        if segment_id == self._greeting_segment:
            self._greeting_segment = None
            await self._listen(self._config.listen_timeout_ms)
            return
        if segment_id not in self._pending_segments:
            return
        self._pending_segments.discard(segment_id)
        await self._maybe_finish_speaking()

    async def cancel(self) -> None:
        """Stop whatever Jarvis is doing and return to idle."""
        if self._enrollment is not None:
            await self._end_enrollment(EnrollmentStatus.CANCELLED)
            return
        await self._stop_everything()
        await self._go_idle()

    async def start_enrollment(self) -> None:
        """Begin recording utterances to create the user's voiceprint."""
        if self._speaker is None or self._stt is None:
            await self._sink.publish(
                ErrorOccurred("Voice ID isn't enabled. Set JARVIS_SPEAKER_VERIFICATION=true.")
            )
            return
        await self._stop_everything()
        self._enrollment = []
        await self._sink.publish(
            EnrollmentProgress(EnrollmentStatus.RECORDING, 0, self._speaker.samples_required)
        )
        await self._listen(self._config.listen_timeout_ms * 2)

    async def announce(self, kind: str, text: str) -> None:
        """Proactively say something (e.g. a reminder); queued while busy."""
        await self._sink.publish(Notification(kind, text))
        if self._is_quiet():
            await self._speak_announcement(text)
        else:
            self._announcements.append((kind, text))

    async def close(self) -> None:
        """Release resources when the client disconnects."""
        await self._stop_everything()
        for task in list(self._background):
            task.cancel()

    # ------------------------------------------------------------- barge-in

    async def _check_barge_in(self, frame: bytes) -> None:
        mode = self._config.barge_in
        if mode == "wake_word" and self._wake is not None and self._wake.process(frame):
            log.info("barge_in", trigger="wake_word")
            await self._interrupt()
        elif mode == "voice" and self._barge_vad is not None:
            if not self._barge_vad.is_speech(frame):
                self._barge_frames.clear()
                return
            self._barge_frames.append(frame)
            needed = self._config.barge_in_min_speech_ms // self._config.frame_ms
            if len(self._barge_frames) >= max(1, needed):
                seed, self._barge_frames = self._barge_frames, []
                log.info("barge_in", trigger="voice")
                await self._interrupt(seed)

    async def _interrupt(self, seed: list[bytes] | None = None) -> None:
        """Cut Jarvis off and listen; ``seed`` = speech already captured."""
        await self._stop_everything()
        await self._sink.publish(Interrupted())
        if self._wake is not None:
            self._wake.reset()
        await self._listen(self._config.listen_timeout_ms)
        for frame in seed or ():
            self._recorder.push(frame)

    # ------------------------------------------------------------- the turn

    async def _on_utterance(self, audio: AudioClip) -> None:
        if self._enrollment is not None:
            await self._collect_enrollment(audio)
        else:
            await self._start_turn(audio=audio)

    async def _start_turn(self, *, audio: AudioClip | None = None, text: str | None = None) -> None:
        # Switch state *before* spawning the task so further frames are routed
        # to barge-in detection instead of the recorder.
        self._pending_segments.clear()
        self._generation_done = False
        self._follow_up_after = True
        self._timer = _TurnTimer(started=self._clock())
        await self._set_state(AssistantState.THINKING)
        self._turn_task = asyncio.create_task(self._run_turn(audio, text), name="jarvis-turn")

    async def _run_turn(self, audio: AudioClip | None, text: str | None) -> None:
        try:
            if text is None:
                text = await self._understand(audio)
                if not text:
                    await self._go_idle()
                    return
            await self._sink.publish(TranscriptReady(text))
            answer = await self._generate_and_speak(text)
            self._history.add_user(text)
            self._history.add_assistant(answer)
            await self._sink.publish(TurnCompleted(answer))
            await self._publish_metrics()
            self._generation_done = True
            await self._maybe_finish_speaking()
        except asyncio.CancelledError:
            raise
        except JarvisError as exc:
            log.warning("turn_failed", error=str(exc))
            await self._fail(str(exc))
        except Exception:
            log.exception("turn_crashed")
            await self._fail(_GENERIC_ERROR)

    async def _understand(self, audio: AudioClip | None) -> str:
        """Verify the speaker, then transcribe. Returns "" to abandon the turn."""
        if audio is None or self._stt is None:
            return ""
        started = self._clock()
        if self._speaker is not None and self._speaker.enrolled:
            accepted, score = await self._speaker.verify(audio)
            if not accepted:
                log.info("speaker_rejected", score=round(score, 3))
                await self._sink.publish(SpeakerRejected(round(score, 3)))
                return ""
        transcript = (await asyncio.to_thread(self._stt.transcribe, audio)).strip()
        if self._timer is not None:
            self._timer.stt_ms = (self._clock() - started) * 1000
        log.info("transcribed", seconds=round(audio.duration_seconds, 2), text=transcript)
        return transcript

    async def _generate_and_speak(self, request: str) -> str:
        """Stream the brain's answer while a parallel task speaks finished sentences."""
        chunker = SentenceChunker()
        sentences: asyncio.Queue[str | None] = asyncio.Queue()
        speaker = (
            asyncio.create_task(self._speak_sentences(sentences), name="jarvis-speaker")
            if self._tts is not None
            else None
        )
        parts: list[str] = []
        try:
            async for event in self._brain.respond(self._history.messages(), request):
                if isinstance(event, ToolUse):
                    if self._timer is not None:
                        self._timer.tools.append(event.name)
                    await self._sink.publish(ToolInvoked(event.name, event.label))
                    continue
                self._mark_first_token(event)
                parts.append(event.text)
                await self._sink.publish(AssistantTextDelta(event.text))
                for sentence in chunker.feed(event.text):
                    sentences.put_nowait(sentence)
            if remainder := chunker.flush():
                sentences.put_nowait(remainder)
            sentences.put_nowait(None)
            if speaker is not None:
                await speaker
        finally:
            if speaker is not None and not speaker.done():
                speaker.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await speaker

        answer = "".join(parts).strip()
        if not answer:
            raise LanguageModelError("The language model returned an empty answer.")
        return answer

    async def _speak_sentences(self, sentences: asyncio.Queue[str | None]) -> None:
        assert self._tts is not None
        while (sentence := await sentences.get()) is not None:
            spoken = to_speakable(sentence)
            if not spoken:
                continue
            speech = await asyncio.to_thread(self._tts.synthesize, spoken)
            if self._timer is not None and self._timer.first_audio is None:
                self._timer.first_audio = self._clock()
            await self._emit_speech(speech, SegmentKind.ANSWER)

    def _mark_first_token(self, _: TextDelta) -> None:
        if self._timer is not None and self._timer.first_token is None:
            self._timer.first_token = self._clock()

    async def _publish_metrics(self) -> None:
        timer = self._timer
        if timer is None:
            return

        def since_start(moment: float | None) -> float | None:
            return None if moment is None else round((moment - timer.started) * 1000, 1)

        total = since_start(self._clock()) or 0.0
        metrics = TurnMetrics(
            stt_ms=None if timer.stt_ms is None else round(timer.stt_ms, 1),
            first_token_ms=since_start(timer.first_token),
            first_audio_ms=since_start(timer.first_audio),
            total_ms=total,
            tools=tuple(timer.tools),
        )
        log.info("turn_metrics", **{k: getattr(metrics, k) for k in metrics.__slots__})
        await self._sink.publish(metrics)

    # ----------------------------------------------------------- enrollment

    async def _collect_enrollment(self, audio: AudioClip) -> None:
        assert self._speaker is not None and self._enrollment is not None
        try:
            self._enrollment.append(await self._speaker.embed(audio))
        except Exception:
            log.exception("enrollment_embedding_failed")
            await self._end_enrollment(EnrollmentStatus.FAILED)
            return
        collected = len(self._enrollment)
        required = self._speaker.samples_required
        if collected < required:
            await self._sink.publish(
                EnrollmentProgress(EnrollmentStatus.RECORDING, collected, required)
            )
            await self._listen(self._config.listen_timeout_ms * 2)
            return
        await self._speaker.enroll(self._enrollment)
        log.info("voice_enrolled", samples=collected)
        await self._end_enrollment(EnrollmentStatus.COMPLETE)

    async def _end_enrollment(self, status: EnrollmentStatus) -> None:
        collected = len(self._enrollment or [])
        required = self._speaker.samples_required if self._speaker else 0
        self._enrollment = None
        await self._sink.publish(EnrollmentProgress(status, collected, required))
        await self._go_idle()

    # -------------------------------------------------------- announcements

    def _is_quiet(self) -> bool:
        turn_active = self._turn_task is not None and not self._turn_task.done()
        return self._state is AssistantState.IDLE and not turn_active and self._enrollment is None

    async def _speak_announcement(self, text: str) -> None:
        if self._tts is None:
            return
        speech = await asyncio.to_thread(self._tts.synthesize, to_speakable(text) or text)
        if not self._is_quiet():  # the user started something meanwhile
            self._announcements.appendleft(("reminder", text))
            return
        self._pending_segments.clear()
        self._generation_done = True
        self._follow_up_after = False
        await self._emit_speech(speech, SegmentKind.ANNOUNCEMENT)

    async def _flush_announcements(self) -> None:
        if self._announcements and self._is_quiet():
            _, text = self._announcements.popleft()
            await self._speak_announcement(text)

    # -------------------------------------------------------------- helpers

    async def _emit_speech(self, speech: SynthesizedSpeech, kind: SegmentKind) -> None:
        segment_id = f"seg-{next(self._segment_ids)}"
        # Register before publishing: the client may answer before we resume.
        if kind is SegmentKind.GREETING:
            self._greeting_segment = segment_id
        else:
            self._pending_segments.add(segment_id)
        self._arm_watchdog(segment_id, speech.audio.duration_seconds)
        await self._set_state(AssistantState.SPEAKING)
        await self._sink.publish(SpeechSegmentReady(segment_id, kind, speech))

    def _arm_watchdog(self, segment_id: str, duration_s: float) -> None:
        """Assume playback ended if the client never acknowledges the segment.

        Segments play back-to-back on the client, so each deadline is measured
        from the expected end of the previous segment, not from now.
        """
        loop = asyncio.get_running_loop()
        now = loop.time()
        self._playback_deadline = max(self._playback_deadline, now) + duration_s
        delay = self._playback_deadline - now + self._config.playback_grace_ms / 1000
        self._watchdogs[segment_id] = loop.call_later(delay, self._on_watchdog, segment_id)

    def _on_watchdog(self, segment_id: str) -> None:
        if self._watchdogs.pop(segment_id, None) is None:
            return
        log.warning("playback_ack_timeout", segment=segment_id)
        self._spawn(self.handle_playback_ended(segment_id))

    async def _maybe_finish_speaking(self) -> None:
        if not self._generation_done or self._pending_segments or self._greeting_segment:
            return
        self._generation_done = False
        if self._follow_up_after and self._config.follow_up_ms > 0:
            await self._listen(self._config.follow_up_ms)
        else:
            await self._go_idle()

    async def _listen(self, timeout_ms: int) -> None:
        if self._stt is None:
            await self._go_idle()
            return
        self._recorder.reset(timeout_ms)
        self._barge_frames.clear()
        await self._set_state(AssistantState.LISTENING)

    async def _go_idle(self) -> None:
        if self._wake is not None:
            self._wake.reset()
        self._barge_frames.clear()
        await self._set_state(AssistantState.IDLE)
        if self._announcements:
            self._spawn(self._flush_announcements())

    async def _fail(self, message: str) -> None:
        self._clear_playback()
        self._generation_done = False
        try:
            await self._sink.publish(ErrorOccurred(message))
            await self._go_idle()
        except Exception:  # the transport itself may be gone (client disconnected)
            log.debug("error_report_failed", exc_info=True)

    async def _set_state(self, state: AssistantState) -> None:
        if state is not self._state:
            self._state = state
            await self._sink.publish(StateChanged(state))

    async def _stop_everything(self) -> None:
        """Cancel generation and forget about in-flight playback."""
        task, self._turn_task = self._turn_task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._clear_playback()
        self._generation_done = False

    def _clear_playback(self) -> None:
        for handle in self._watchdogs.values():
            handle.cancel()
        self._watchdogs.clear()
        self._pending_segments.clear()
        self._greeting_segment = None
        self._playback_deadline = 0.0

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coroutine)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
