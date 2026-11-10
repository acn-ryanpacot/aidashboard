# 0004. Python core service with a WebSocket voice transport

- Status: Accepted
- Date: 2026-11-10

## Context

The best free speech and AI libraries are Python-first. The UI must be a premium web-technology front end. Future mobile apps should share the same brain. Audio must flow both ways with low latency, and the UI needs exact word timings to sync captions with playback.

## Decision

- Run a separate **FastAPI** process (`services/core`), bound to loopback.
- One **WebSocket per client** (`/ws/voice`):
    - **Up:** raw PCM16 at 16 kHz in 80 ms frames. That is openWakeWord's native frame, so no re-chunking is needed on the server. Resampling happens in an AudioWorklet in the client.
    - **Down:** JSON events, plus a WAV binary frame after each `speech_segment` header.
- **The client plays the audio.** Playback goes through Web Audio, so the UI owns the `AnalyserNode` that drives the visualizer and the clock that drives captions.

Alternatives considered: WebRTC (overkill for a local link, with complex signalling), server-side playback (the UI couldn't visualize or caption accurately), and an all-in-browser Web Speech API (Chrome's implementation streams audio to the cloud).

## Consequences

- **+** The visualizer and captions are sample-accurate. The UI works in a browser and in Tauri alike.
- **+** Mobile apps can reuse the protocol or REST endpoints later.
- **−** Uncompressed PCM costs about 32 KB/s upstream. That's negligible on loopback but worth revisiting (Opus) for remote mobile use.
- **−** Two processes to run in development. Packaging the core as a Tauri sidecar is Phase 5.
