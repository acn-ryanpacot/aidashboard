# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org).

## [Unreleased]

## [0.2.0] - 2026-11-10

Phases 2 (voice polish) and 3 (the brain).

### Added

- **Brain**: bounded tool-calling agent loop over Ollama (`tools` API), with a `ToolRegistry` that turns every failure into a message for the model.
- **Built-in tools**: current time; tasks (add, list, complete); reminders (set, list, cancel, spoken when due); long-term memory (remember, recall, forget); weather (Open-Meteo); encyclopedia (Wikipedia); web search (SearXNG, optional); local document search (RAG, optional).
- **MCP client**: launch stdio MCP servers from `JARVIS_MCP_SERVERS` and expose their tools as `server__tool`.
- **Long-term memory**: embeddings via Ollama `nomic-embed-text`, relevant memories injected into each prompt, keyword fallback.
- **Persistence**: SQLite (`~/.jarvis-os/jarvis.db`) with versioned migrations; REST API for tasks, reminders, memories and the voiceprint.
- **Reminder scheduler** and `SessionHub`: announcements spoken on every idle client; `data_changed` broadcasts refresh widgets live.
- **Barge-in** (`wake_word` / `voice` / `off`), **push-to-talk** (`listen` message, Ctrl+Space, global Ctrl+Shift+Space in Tauri).
- **Voice ID**: SpeechBrain ECAPA verification and in-app enrollment (`enroll_voice`), optional `speaker` extra.
- **Silero VAD** adapter (`JARVIS_VAD_ENGINE=silero`).
- **Playback watchdog** and per-turn **latency metrics** (`metrics` message).
- **Persona styles**: formality, verbosity and humour settings.
- **UI**: earcons (synthesized), sound toggle, live Tasks widget with reminders, Systems widget with barge-in, tools, voice-ID enrollment and latency, enrollment overlay, tool-activity hints ("Checking the weather…"), reminder entries in the conversation.
- Docs: brain architecture, voice-ID, knowledge-source, MCP and adding-a-tool guides; ADRs 0007–0010.

### Changed

- Voice protocol bumped to **v2** (backwards-incompatible additions to `ready`).
- `LanguageModel.stream_chat` now yields `TextDelta | ToolCall` and accepts tool specs.
- `VoiceSession` depends on `Brain` instead of the raw language model.
- The Tasks dashboard tile is now a real, core-backed widget.

## [0.1.0] - 2026-11-10

### Added

- Monorepo (pnpm workspaces + uv) with CI, pre-commit hooks, ESLint/Prettier, Ruff/mypy.
- **Core service** (FastAPI): hexagonal architecture with ports for wake word, VAD, STT, LLM, TTS and event sink.
- Voice session state machine: wake → cached greeting → listen → think → speak, follow-up mode, cancel, text queries.
- Adapters: openWakeWord, WebRTC VAD, energy VAD, faster-whisper, Ollama (streaming), Kokoro TTS with word timings.
- `/ws/voice` protocol (PCM16 up, JSON + WAV down) and `/api/health`.
- **Desktop UI**: engage screen, reactive canvas orb, karaoke captions, command bar (Ctrl+K / Esc), status bar.
- Widget SDK (`@jarvis/widget-sdk`) with manifest validation and registry. Built-in widgets: Chronometer, Systems, Conversation. Placeholders for the Schedule, Tasks and Briefing mobile apps.
- Tauri 2 shell with strict CSP and least-privilege capabilities.
- Documentation site (MkDocs Material), ADRs 0001–0006, guides and design system.
