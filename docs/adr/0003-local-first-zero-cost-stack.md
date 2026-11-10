# 0003. Local-first, zero-cost AI stack

- Status: Accepted
- Date: 2026-11-10

## Context

Jarvis OS is for personal use. The requirement is no recurring cost and no subscriptions. A microphone that is always listening also raises privacy concerns, which favour on-device processing.

## Decision

| Capability | Choice                      | License         | Why                                                            |
| ---------- | --------------------------- | --------------- | -------------------------------------------------------------- |
| Wake word  | openWakeWord                | Apache-2.0      | Free custom models, pretrained `hey_jarvis`, runs on CPU       |
| VAD        | WebRTC VAD (`webrtcvad-wheels`) | BSD-style   | Tiny, no PyTorch dependency for streaming endpointing          |
| STT        | faster-whisper              | MIT             | Whisper accuracy at roughly 4× speed; int8 on CPU              |
| LLM        | Ollama + open-weight model  | MIT (runtime)   | One-command model management, streaming API, GPU/CPU           |
| TTS        | Kokoro-82M                  | Apache-2.0      | Near-commercial quality, fast on CPU, **word timestamps**, British voices |

Cloud services (free tiers or paid APIs) are allowed **only** as optional adapters behind the same ports, never as defaults.

## Consequences

- **+** No cost, no account, works offline, and audio never leaves the machine.
- **+** Word timestamps from Kokoro enable precise karaoke captions.
- **−** Quality is bounded by local hardware. A 3B model on CPU is less capable than frontier cloud models. Mitigation: a GPU lets you use larger models, and a cloud adapter can be added later without touching the application layer.
- **−** First install is large (about 2 GB of Python wheels plus about 500 MB of models).
