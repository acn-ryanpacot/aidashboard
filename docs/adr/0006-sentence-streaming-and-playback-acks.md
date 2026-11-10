# 0006. Sentence-level speech streaming with playback acknowledgements

- Status: Accepted
- Date: 2026-11-10

## Context

Waiting for the full LLM answer before speaking adds seconds of dead air. Streaming TTS at the token level produces choppy prosody. Separately, the server must not listen while Jarvis is speaking, or it hears itself, and it can only know when playback has ended if the client tells it.

## Decision

- `SentenceChunker` emits complete sentences from the LLM stream, merging fragments shorter than 20 characters. A producer/consumer queue synthesizes sentence *n* while the model writes *n+1*.
- Each synthesized sentence is a **segment** with an id. The client schedules segments gaplessly on its `AudioContext` and sends `playback_ended` for each.
- The session leaves `speaking` only after the generation is finished **and** every segment has been acknowledged.
- The wake-word greeting is a segment too (`kind: greeting`). Listening starts only after its acknowledgement.

## Consequences

- **+** Time to first audio drops to roughly one sentence of LLM plus TTS time. Prosody stays natural within sentences.
- **+** The mic is never processed while Jarvis talks, which prevents self-triggering.
- **−** A client that never acknowledges leaves the session in `speaking`. Clients without audio must acknowledge immediately (the UI does this before "Engage"). A server-side safety timeout is a possible future hardening.
- **−** Barge-in (interrupting mid-answer) needs extra work (Phase 2): echo-cancelled wake detection while speaking.
