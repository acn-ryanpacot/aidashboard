"""The voice session: Jarvis's conversational state machine.

One :class:`VoiceSession` exists per connected client. It consumes microphone
frames and client commands, and publishes :mod:`~jarvis_core.domain.events`
through a :class:`~jarvis_core.domain.ports.VoiceEventSink`.

State diagram::

            wake word / activate()
    IDLE ─────────────────────────────▶ SPEAKING (greeting)
     ▲                                     │ playback_ended
     │ timeout                             ▼
     ├──────────────────────────────── LISTENING ◀──────────────┐
     │                                     │ end of speech       │ follow-up
     │                                     ▼   (or text query)   │ window
     │                                 THINKING                  │
     │                                     │ first sentence      │
     │                                     ▼                     │
     └──── (follow-up disabled) ────── SPEAKING (answer) ────────┘
                                        last playback_ended

Concurrency model: all public ``handle_*`` methods are called sequentially
from the transport's receive loop. Generating an answer runs in a separate
task (so the loop keeps receiving ``playback_ended`` / ``cancel``), and
blocking model calls run in worker threads via :func:`asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
from dataclasses import dataclass

import structlog

from jarvis_core.application.conversation import ConversationHistory
from jarvis_core.application.endpointing import (
    ListeningTimedOut,
    UtteranceComplete,
    UtteranceRecorder,
)
from jarvis_core.application.greeting import GreetingCache
from jarvis_core.application.persona import Persona
from jarvis_core.application.sentence_chunker import SentenceChunker
from jarvis_core.application.speech_text import to_speakable
from jarvis_core.domain.errors import JarvisError, LanguageModelError
from jarvis_core.domain.events import (
    AssistantTextDelta,
    ErrorOccurred,
    SegmentKind,
    SpeechSegmentReady,
    StateChanged,
    TranscriptReady,
    TurnCompleted,
    WakeDetected,
)
from jarvis_core.domain.models import (
    AssistantState,
    AudioClip,
    ChatMessage,
    Role,
    SynthesizedSpeech,
)
from jarvis_core.domain.ports import (
    LanguageModel,
    SpeechToText,
    TextToSpeech,
    VoiceEventSink,
    WakeWordDetector,
)

log = structlog.get_logger(__name__)

_GENERIC_ERROR = "I'm afraid something went wrong on my side. Please try again."


@dataclass(frozen=True, slots=True)
class SessionConfig:
    """Behavioural settings for a :class:`VoiceSession` (milliseconds).

    Attributes:
        listen_timeout_ms: How long to wait for speech after the greeting.
        follow_up_ms: How long to keep listening after an answer without
            requiring the wake word again. ``0`` disables follow-up mode.
    """

    listen_timeout_ms: int = 6_000
    follow_up_ms: int = 6_000


class VoiceSession:
    """Orchestrates wake → greet → listen → think → speak for one client.

    Args:
        sink: Where events are published.
        persona: Assistant identity and system prompt.
        greeting: Cached wake-word greeting.
        llm: Language model.
        recorder: Endpointing for spoken requests.
        history: Short-term conversation memory.
        stt: Speech recognition, or ``None`` for text-only mode.
        tts: Speech synthesis, or ``None`` for text-only mode.
        wake: Wake-word detector, or ``None`` to rely on manual activation.
        config: Timing behaviour.
    """

    def __init__(
        self,
        *,
        sink: VoiceEventSink,
        persona: Persona,
        greeting: GreetingCache,
        llm: LanguageModel,
        recorder: UtteranceRecorder,
        history: ConversationHistory,
        stt: SpeechToText | None = None,
        tts: TextToSpeech | None = None,
        wake: WakeWordDetector | None = None,
        config: SessionConfig | None = None,
    ) -> None:
        self._sink = sink
        self._persona = persona
        self._greeting = greeting
        self._llm = llm
        self._recorder = recorder
        self._history = history
        self._stt = stt
        self._tts = tts
        self._wake = wake
        self._config = config or SessionConfig()

        self._state = AssistantState.IDLE
        self._turn_task: asyncio.Task[None] | None = None
        self._segment_ids = itertools.count(1)
        self._greeting_segment: str | None = None
        self._pending_segments: set[str] = set()
        self._generation_done = False

    # ------------------------------------------------------------ public API

    @property
    def state(self) -> AssistantState:
        """The current assistant state."""
        return self._state

    async def start(self) -> None:
        """Announce the initial state to the client."""
        await self._sink.publish(StateChanged(self._state))

    async def handle_audio(self, frame: bytes) -> None:
        """Process one 80 ms microphone frame (16 kHz mono PCM16)."""
        if self._state is AssistantState.IDLE:
            if self._wake is not None and self._wake.process(frame):
                log.info("wake_word_detected")
                await self.activate()
        elif self._state is AssistantState.LISTENING:
            event = self._recorder.push(frame)
            if isinstance(event, UtteranceComplete):
                await self._start_turn(audio=event.audio)
            elif isinstance(event, ListeningTimedOut):
                log.info("listening_timed_out")
                await self._go_idle()
        # THINKING / SPEAKING: frames are ignored (barge-in is a planned feature).

    async def activate(self) -> None:
        """Greet the user and start listening (wake word or manual trigger)."""
        await self._cancel_turn()
        if self._wake is not None:
            self._wake.reset()
        await self._sink.publish(WakeDetected())
        speech = await self._greeting.get()
        if speech is None:
            await self._sink.publish(TurnCompleted(self._greeting.text))
            await self._listen(self._config.listen_timeout_ms)
        else:
            await self._emit_speech(speech, SegmentKind.GREETING)

    async def handle_text_query(self, text: str) -> None:
        """Answer a typed question, bypassing wake word and speech recognition."""
        text = text.strip()
        if not text:
            return
        await self._cancel_turn()
        self._greeting_segment = None
        await self._start_turn(text=text)

    async def handle_playback_ended(self, segment_id: str) -> None:
        """The client finished playing a speech segment."""
        if segment_id == self._greeting_segment:
            self._greeting_segment = None
            await self._listen(self._config.listen_timeout_ms)
            return
        self._pending_segments.discard(segment_id)
        await self._maybe_finish_speaking()

    async def cancel(self) -> None:
        """Stop whatever Jarvis is doing and return to idle."""
        await self._cancel_turn()
        self._greeting_segment = None
        await self._go_idle()

    async def close(self) -> None:
        """Release resources when the client disconnects."""
        await self._cancel_turn()

    # ------------------------------------------------------------- the turn

    async def _start_turn(self, *, audio: AudioClip | None = None, text: str | None = None) -> None:
        # Switch state *before* spawning the task so further frames are ignored.
        self._pending_segments.clear()
        self._generation_done = False
        await self._set_state(AssistantState.THINKING)
        self._turn_task = asyncio.create_task(self._run_turn(audio, text), name="jarvis-turn")

    async def _run_turn(self, audio: AudioClip | None, text: str | None) -> None:
        try:
            if text is None:
                text = await self._transcribe(audio)
                if not text:
                    log.info("empty_transcript")
                    await self._go_idle()
                    return
            await self._sink.publish(TranscriptReady(text))
            answer = await self._generate_and_speak(text)
            self._history.add_user(text)
            self._history.add_assistant(answer)
            await self._sink.publish(TurnCompleted(answer))
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

    async def _transcribe(self, audio: AudioClip | None) -> str:
        if audio is None or self._stt is None:
            return ""
        transcript = await asyncio.to_thread(self._stt.transcribe, audio)
        log.info("transcribed", seconds=round(audio.duration_seconds, 2), text=transcript)
        return transcript.strip()

    async def _generate_and_speak(self, user_text: str) -> str:
        """Stream the LLM answer while a parallel task speaks finished sentences."""
        messages = [
            self._persona.system_message(),
            *self._history.messages(),
            ChatMessage(Role.USER, user_text),
        ]
        chunker = SentenceChunker()
        sentences: asyncio.Queue[str | None] = asyncio.Queue()
        speaker = (
            asyncio.create_task(self._speak_sentences(sentences), name="jarvis-speaker")
            if self._tts is not None
            else None
        )
        parts: list[str] = []
        try:
            async for delta in self._llm.stream_chat(messages):
                parts.append(delta)
                await self._sink.publish(AssistantTextDelta(delta))
                for sentence in chunker.feed(delta):
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
            await self._emit_speech(speech, SegmentKind.ANSWER)

    # -------------------------------------------------------------- helpers

    async def _emit_speech(self, speech: SynthesizedSpeech, kind: SegmentKind) -> None:
        segment_id = f"seg-{next(self._segment_ids)}"
        # Register before publishing: the client may answer before we resume.
        if kind is SegmentKind.GREETING:
            self._greeting_segment = segment_id
        else:
            self._pending_segments.add(segment_id)
        await self._set_state(AssistantState.SPEAKING)
        await self._sink.publish(SpeechSegmentReady(segment_id, kind, speech))

    async def _maybe_finish_speaking(self) -> None:
        if not self._generation_done or self._pending_segments or self._greeting_segment:
            return
        self._generation_done = False
        if self._config.follow_up_ms > 0:
            await self._listen(self._config.follow_up_ms)
        else:
            await self._go_idle()

    async def _listen(self, timeout_ms: int) -> None:
        if self._stt is None:
            await self._go_idle()
            return
        self._recorder.reset(timeout_ms)
        await self._set_state(AssistantState.LISTENING)

    async def _go_idle(self) -> None:
        if self._wake is not None:
            self._wake.reset()
        await self._set_state(AssistantState.IDLE)

    async def _fail(self, message: str) -> None:
        self._pending_segments.clear()
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

    async def _cancel_turn(self) -> None:
        task, self._turn_task = self._turn_task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._pending_segments.clear()
        self._generation_done = False
