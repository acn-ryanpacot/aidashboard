# 0013. Echo-aware voice barge-in on the client

- Status: Accepted
- Date: 2026-11-10
- Supersedes the `voice` mode of: [0009](0009-barge-in-and-playback-watchdog.md)

## Context

ADR-0009's `voice` barge-in ran a VAD on the server over raw microphone frames while Jarvis spoke. Through loudspeakers the microphone hears Jarvis, so Jarvis interrupted itself. Browser echo cancellation helps, but it isn't guaranteed to cancel audio played through Web Audio.

## Decision

- Detection moves to the **client**, the only place that knows both signals at the same instant: the mic frame, and what the speakers are playing (the `SpeechPlayer`'s analyser).
- `EchoGate` (double-talk detection) works like this:
    - It continuously estimates the speaker→mic **leak ratio** while only Jarvis is talking, and the room's **noise floor** while nothing plays.
    - A frame counts as user speech only if mic RMS > max(min level, 3× noise floor, 2.2× leak × recent output). "Recent output" is the maximum over the last ~320 ms, to cover echo delay.
    - It requires `barge_in_min_speech_ms` of consecutive speech (400 ms by default).
- On trigger, the client stops playback, sends `{"type":"barge_in"}`, then replays the last ~800 ms of mic frames, so the new request includes the first words.
- The server accepts `barge_in` only in `voice` mode while thinking or speaking. The wake word interrupts in both `wake_word` and `voice` modes.

## Consequences

- **+** Talking over Jarvis works through speakers in ordinary rooms, and Jarvis no longer interrupts itself with its own voice.
- **+** Pure, unit-tested logic (`echoGate.ts`). Thresholds are tunable from Settings.
- **−** A heuristic, not full acoustic echo cancellation. Very loud playback, or a microphone right next to the speaker, can still cause misses or false triggers. A headset, or `wake_word` mode, remains the most robust option.
