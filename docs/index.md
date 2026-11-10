# Jarvis OS

Jarvis OS is a personal operating surface: a full-screen dashboard of widgets with a voice-driven AI at its centre.

![Engage screen](assets/engage-screen.jpg)

## What it does today (Phase 1)

| Capability              | How                                                                  |
| ----------------------- | -------------------------------------------------------------------- |
| Always-on wake word     | openWakeWord listens locally for "Hey Jarvis" (or your custom model) |
| Fixed greeting          | "How can I help you Ryan?", synthesized once and replayed instantly  |
| Understanding speech    | WebRTC VAD finds the end of your sentence; faster-whisper transcribes |
| Answering               | A local LLM via Ollama, streamed sentence by sentence                |
| Speaking                | Kokoro TTS with per-word timestamps                                  |
| Looking alive           | Canvas orb driven by the live audio spectrum, plus karaoke captions  |
| Typing instead          | Command bar (Ctrl+K). Esc interrupts                                 |
| Dashboard               | Widget SDK + registry; Clock, Systems, Conversation, app placeholders |

## Where to go next

- New here? Start with [Getting started](getting-started.md).
- To understand the design, read the [Architecture overview](architecture/overview.md).
- To extend it, see the [Guides](guides/adding-a-widget.md).
- For past decisions and their reasons, see the [Decision records](adr/index.md).
