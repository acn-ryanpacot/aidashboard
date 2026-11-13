# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org).

## [Unreleased]

### Added

- **Web search works out of the box** ([guide](docs/guides/web-search.md), [ADR-0017](docs/adr/0017-knowledge-sources.md)):
  - DuckDuckGo with no setup, or your own **SearXNG** first when `JARVIS_SEARXNG_URL` is set (`JARVIS_WEB_SEARCH=auto`).
  - A ready SearXNG setup in `services/searxng` (`docker compose up -d`, loopback only).
  - Jarvis reads the relevant parts of the top two result pages and names the sites.
  - E-mails and long ID-like numbers are stripped from queries, and pages on your own network are never fetched.
  - When DuckDuckGo shows a captcha, Jarvis backs off for five minutes.
- **Your documents folder** (Settings → **Knowledge**):
  - Jarvis now reads **PDF, Word (`.docx`), Excel (`.xlsx`) and CSV** files as well as notes, and answers from them, naming the file.
  - New `read_spreadsheet` tool: exact totals, largest, smallest and averages per column, with an optional row filter ("how much do I owe in total?", "…on the BDO card?").
  - New `list_documents` tool.
  - The folder is a live setting (PC only). Settings shows indexing progress and unreadable files with the reason (e.g. scanned PDFs), and has a **Re-index now** button. New files are picked up every five minutes.
  - `GET /api/knowledge`, `POST /api/documents/reindex`.
- The system prompt lists the abilities Jarvis really has, so he no longer says he can't search the web or read your files.
- `jarvis-doctor` checks web search and the documents folder.

- **Notifications center**:
  - Every announcement (timers, reminders, stock alerts, briefings) is recorded, including ones made while no window was open (migration 6; last 30 days, at most 500 entries).
  - A **bell** in the top bar with an unread badge opens a drawer grouped by day. Opening it marks everything read, and what was new stays highlighted. Also in the command palette.
  - *"What did I miss?"* reads the unread ones aloud (`get_notifications` tool, new `notifications` routing group).
  - REST: `GET /api/notifications`, `POST /api/notifications/read`, `DELETE /api/notifications`.

- **Phone access via Tailscale** ([guide](docs/guides/phone-access.md), [ADR-0016](docs/adr/0016-phone-access.md)):
  - Use Jarvis from your phone over `tailscale serve` (HTTPS, so the phone microphone works). The core stays on loopback and nothing is exposed on the LAN.
  - **Device tokens:** stored as SHA-256 hashes (migration 5), required for every request relayed by a proxy or from another address. Sent as `Authorization: Bearer` on HTTP and as a `bearer.…` WebSocket subprotocol (close code 4401 when unpaired), so they never appear in URLs.
  - **Settings → Phone access:** a setup checklist (Tailscale connected, published, dashboard built), **Pair a phone** with a QR code, and paired devices with last use and **Revoke**. Device management is local-only.
  - **On the phone:** a pairing screen, a responsive one-column layout, and installable as a home-screen app (web manifest).
  - The core serves the built dashboard at `/` (`JARVIS_WEB_DIST`). New `jarvis-token` CLI (`create`, `list`, `revoke`). `jarvis-doctor` checks Tailscale and the dashboard build.

- **PisoTiyempo Portfolio widget**, the first companion-app widget ([guide](docs/guides/pisotiyempo.md), [ADR-0015](docs/adr/0015-companion-app-feeds.md)):
  - Your PSE holdings for today or the last session, with day change, value, P/L and the biggest movers.
  - When you hold nothing, three **trend-and-value ideas** with their reasons, labelled as ideas to research.
  - Reads PisoTiyempo's local feed, falling back to its export files; core route `/api/apps/pisotiyempo`.
- Voice tools `get_portfolio` and `get_stock_ideas` (new `stocks` routing group), and a portfolio line in the morning briefing.
- Settings → **Companion apps** → PisoTiyempo feed address (live). New variables `JARVIS_PORTFOLIO_ENABLED`, `JARVIS_PORTFOLIO_FEED_URL` and `JARVIS_PORTFOLIO_EXPORT_DIR`.
- `jarvis-doctor` checks PisoTiyempo, and detects PisoTiyempo's feed occupying port 8765.
- Settings drawer: **Ctrl+S**, or Enter in a text field, saves.
- **Timers**:
  - *"Jarvis, 10 minutes for the rice"*, with tools `set_timer`, `list_timers` and `cancel_timer` (new `timers` routing group).
  - A **Timers** widget with countdown rings, presets and a free-text box (`12 min tea`).
  - A distinct three-part chime that rings even in focus mode.
  - Timers are stored in SQLite (migration 4), with REST at `/api/timers`.
- **Spoken PisoTiyempo alerts**:
  - Your price above/below, Buy/Sell signal and pattern alerts are checked with the phone app's own conditions and announced once per trading day.
  - They wait for an open window instead of being lost, and show as a gold line in the Portfolio widget.
  - Ask with `get_stock_alerts`.
  - Alerts are read read-only from PisoTiyempo's database. New variables `JARVIS_PORTFOLIO_ALERTS_ENABLED`, `JARVIS_PORTFOLIO_DATABASE` and `JARVIS_PORTFOLIO_ALERTS_POLL_S`.

### Fixed

- When a data source fails (e.g. web search is down), Jarvis now hears the reason instead of "the tool failed unexpectedly", so he can say what's wrong.
- The Settings drawer no longer silently discards unsaved changes when closed. It asks whether to save or discard.
- Desktop shell: `app.path()` failed to compile (missing `tauri::Manager` import in `core_service`).
- Docs: install pnpm with `npm install -g` (no admin, works on Node 25+); Smart App Control blocking uv's Python on Windows 11.

## [0.3.0] - 2026-11-10

Phase 4 (dashboard) plus the carried-forward items.

### Added

- **Editable dashboard**: drag tiles between sides, resize (1–4 rows), add/remove from a widget gallery; layout saved to the core service (`/api/ui-preferences/layout`) with a local fallback.
- **New widgets**: Weather (Open-Meteo), Schedule (ICS calendars: Google/Outlook/Apple/files, recurring events expanded), Briefing (RSS/Atom headlines), Memory (view and forget), Machine (CPU/RAM/GPU via psutil + nvidia-smi). The Tasks widget is unchanged.
- **Morning briefing**: `daily_briefing` tool ("good morning, Jarvis"), a **Brief me** button, and an optional daily spoken briefing at a set time (delivered once per day, persisted across restarts).
- New tools: `get_headlines`, `get_schedule`, `daily_briefing`, with routing groups.
- **Command palette** (Ctrl/⌘+K): actions plus "ask Jarvis" for free text.
- **Themes** Arctic, Stark Gold and Stealth (CSS variables; the orb follows), **focus mode**, **ambient mode** (screensaver clock after inactivity).
- **Live Settings screen**: persona, voice and speed, wake sensitivity, end-of-speech pause, follow-up, barge-in, voice-ID strictness and training, LLM model (from installed Ollama models), home location, briefing time, news feeds, calendars, appearance. Applied without restart ([ADR-0012](docs/adr/0012-runtime-settings.md)).
- **Echo-aware voice barge-in** through speakers: client-side double-talk detection with pre-roll replay ([ADR-0013](docs/adr/0013-echo-aware-barge-in.md)).
- **Desktop app launches the core service** (and stops it on exit) unless one is already running ([ADR-0014](docs/adr/0014-desktop-launches-core.md)); experimental PyInstaller bundle script.
- **`jarvis-doctor`**: one command that checks Python, Ollama and models, every speech package, NVIDIA driver, PyTorch CUDA and Whisper GPU support, with fix hints.
- **GPU/CPU PyTorch extras** (`--extra cu128` / `--extra cpu`) via uv indexes.
- `JARVIS_LLM_THINK` and automatic hiding of `<think>` blocks from reasoning models.
- Docs: step-by-step **personal GPU PC setup guide**, dashboard guide, ADRs 0012–0014.

### Changed

- Protocol **v3**: client `barge_in` message, `ready.barge_in_min_speech_ms`; server-side VAD barge-in removed in favour of the client detector.
- The persona prompt and greeting follow live settings; `data_changed: settings` notifies clients.
- Weather is available to widgets even when tools are disabled.

### Changed

- **Per-request tool routing** (`JARVIS_TOOL_ROUTING=auto`): only the tool groups a request needs are attached, chosen by keywords, the previous user message and an optional embedding fallback. On a CPU-only laptop with `llama3.2:3b`, chit-chat turns drop from ~17 s to ~2.3 s and tool turns from 17–30 s to ~7–9 s, with fewer spurious tool calls ([ADR-0011](docs/adr/0011-tool-routing.md)).
- The system prompt keeps a stable prefix (date and part of day, variable lines last) so Ollama can reuse its prompt cache; exact times come from the `get_current_time` tool.

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
