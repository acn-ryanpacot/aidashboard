# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org).

## [Unreleased]

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
