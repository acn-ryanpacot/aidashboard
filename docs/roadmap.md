# Roadmap

## Phase 1: Foundation and voice loop ✅ (v0.1.0)

- Monorepo, CI, docs site, ADRs, design tokens
- Core service with a hexagonal architecture and the voice state machine
- Wake word → cached greeting → listen → transcribe → stream → speak
- Reactive orb, karaoke captions, command bar
- Widget SDK, registry, built-in widgets, mobile-app placeholders
- Tauri shell

## Phase 2: Voice polish ✅ (v0.2.0)

- **Barge-in**: say the wake word, or just talk, to interrupt Jarvis mid-sentence ([ADR-0009](adr/0009-barge-in-and-playback-watchdog.md))
- Push-to-talk: Ctrl+Space in the window, Ctrl+Shift+Space system-wide (Tauri global shortcut)
- UI sound design: synthesized earcons for listening, heard, notifications and errors
- Voice ID: SpeechBrain ECAPA speaker verification with in-app enrollment ([ADR-0010](adr/0010-voice-id.md))
- Silero VAD adapter; per-turn latency metrics in the Systems widget
- Playback watchdog, so Jarvis can never get stuck "speaking"

## Phase 3: The brain ✅ (v0.2.0)

- LLM **tool calling** with a bounded agent loop ([ADR-0007](adr/0007-tool-calling-agent-loop.md))
- Tools: time, tasks, reminders (spoken when due), memory, weather, encyclopedia, web search, documents
- Long-term memory in SQLite with Ollama embeddings, keyword fallback and an audit API ([ADR-0008](adr/0008-sqlite-persistence.md))
- Persona settings (formality, verbosity, humour)
- Local document search (RAG) and SearXNG web search
- MCP client: external tool servers plug straight into the brain
- The Tasks widget is now live, backed by `/api/tasks` and refreshed by `data_changed` events

### Carried forward

- ~~Echo-aware `voice` barge-in through speakers~~ (done in v0.3.0)
- ~~A Memories widget and a persona editor in the UI~~ (done in v0.3.0)
- Parallel tool calls

## Phase 4: Dashboard ✅ (v0.3.0)

- User-editable layout: drag between sides, resize, add/remove; saved to the core service
- Built-in widgets: Weather (Open-Meteo), News (RSS/Atom), Schedule (ICS: Google/Outlook/Apple), Machine monitor, Memory
- Morning briefing: spoken summary of weather, schedule, headlines and reminders
- Command palette, themes (Arctic, Stark Gold, Stealth), ambient/screensaver mode, focus mode

Also shipped in v0.3.0 from the carried-forward list: echo-aware `voice` barge-in through speakers ([ADR-0013](adr/0013-echo-aware-barge-in.md)), a live Settings screen ([ADR-0012](adr/0012-runtime-settings.md)), a Memory widget, and the desktop app launching the core ([ADR-0014](adr/0014-desktop-launches-core.md)).

## Phase 5: Desktop integration

- Core service bundled as a Tauri sidecar (PyInstaller), so one installer does everything
- System tray, autostart, always-on-top mini-orb
- Notifications center

## Phase 6: Mobile apps

- Secure remote access to the core service via Tailscale
- Token auth for devices; OpenAPI-generated clients
- Replace placeholders with real Tasks, Schedule and News widgets fed by your apps
- ✅ First companion app: **PisoTiyempo** Portfolio widget, voice tools and briefing line ([ADR-0015](adr/0015-companion-app-feeds.md))
- Push notifications from apps to the dashboard (e.g. PisoTiyempo price alerts)

## Feature ideas backlog

Timers and alarms · unit/currency conversion · clipboard summarizer · daily voice journal · habit tracker · Home Assistant control · webcam presence greeting (MediaPipe) · offline mode indicator · multi-language support
