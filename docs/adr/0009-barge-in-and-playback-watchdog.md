# 0009. Barge-in modes and a playback watchdog

- Status: Accepted
- Date: 2026-11-10
- Amends: [0006](0006-sentence-streaming-and-playback-acks.md)
- `voice` mode superseded by: [0013](0013-echo-aware-barge-in.md)

## Context

In Phase 1 the microphone was ignored while Jarvis spoke, so it couldn't hear itself. The only way to interrupt was a key press. ADR-0006 also noted a risk: a client that never acknowledges playback leaves the session stuck in `speaking`.

## Decision

**Barge-in** is configurable (`JARVIS_BARGE_IN`):

- `wake_word` (default): the client streams audio while Jarvis thinks or speaks, and only the wake-word detector sees it. Jarvis's own speech almost never contains the wake phrase, so this is robust even through speakers.
- `voice`: a separate VAD instance requires a run of continuous speech (≥ 400 ms) before interrupting, which rejects clicks and echo blips. The triggering frames seed the new recording, so no words are lost. Recommended only with a headset or good acoustic echo cancellation.
- `off`.

On interruption the server cancels generation, clears all playback bookkeeping, sends `interrupted` (the client stops audio immediately) and listens.

**Watchdog.** Each segment's deadline is the *expected end of playback* plus `JARVIS_PLAYBACK_GRACE_MS`. Because segments play back-to-back, deadlines accumulate from the previous segment's expected end, not from emission time. An unacknowledged segment is treated as played when its deadline passes.

## Consequences

- **+** Natural interruptions, with no way to get permanently stuck.
- **+** All of it is testable with fakes: barge-in by wake word or voice, streak resets, and watchdog expiry.
- **−** Mic audio is streamed for longer (idle → speaking). That's negligible on loopback.
- **−** `voice` mode depends on the browser's echo cancellation quality.
