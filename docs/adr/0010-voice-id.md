# 0010. Voice ID with ECAPA embeddings and in-app enrollment

- Status: Accepted
- Date: 2026-11-10

## Context

An always-listening assistant in a shared space will hear other people and the TV. The user wants Jarvis to respond only to them, with zero cost and no cloud.

## Decision

- **Model:** SpeechBrain `spkrec-ecapa-voxceleb` (Apache-2.0, about 80 MB), behind the `SpeakerEncoder` port. It is an optional `speaker` extra.
- **Enrollment in the UI.** `enroll_voice` puts the session into a recording mode that captures N utterances (default 3) through the normal endpointing pipeline, embeds each, and stores the L2-normalised **mean** as the voiceprint (`VoiceprintStore` port, a JSON file in the data directory). Enrollment utterances never reach STT or the LLM.
- **Verification** runs inside the turn task *before* STT. Cosine similarity below `JARVIS_SPEAKER_THRESHOLD` publishes `speaker_rejected` and returns to idle. Until someone enrolls, every voice is accepted.
- Off by default, because it adds a dependency and about 100 ms per turn.

## Consequences

- **+** Fully local, a one-minute setup, re-trainable at any time, and removable via `DELETE /api/voiceprint`.
- **+** The embedding is not a recording. It can't be replayed or turned back into audio.
- **−** Not a security boundary: a recording of the user's voice passes. This is documented.
- **−** Thresholds depend on the microphone and room, so the guide explains how to tune them from logged scores.
