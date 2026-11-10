# 0002. Hexagonal architecture for the core service

- Status: Accepted
- Date: 2026-11-10

## Context

The voice pipeline combines five fast-moving third-party engines (wake word, VAD, STT, LLM, TTS). Each is likely to be replaced at least once as better free models appear. The orchestration logic (turn-taking, endpointing, streaming) is the valuable, subtle part, and it must be testable without loading gigabytes of models.

## Decision

Use ports and adapters:

- `domain/ports.py` defines `Protocol` interfaces. Adapters satisfy them structurally and never import them.
- `application/` holds use cases (`VoiceSession`, `UtteranceRecorder`, `SentenceChunker`) and depends only on the domain.
- `adapters/` wrap third-party SDKs, importing them lazily and translating their errors into domain errors.
- `container.py` is the single composition root that selects adapters from `Settings`.

## Consequences

- **+** The state machine is covered by fast, deterministic tests using fakes (`tests/fakes.py`).
- **+** Engines are swappable by configuration. The service runs text-only without the speech extras.
- **+** CI doesn't need PyTorch or model downloads.
- **−** Slightly more files and indirection than a script. Adapter behaviour against real models needs manual or integration testing.
