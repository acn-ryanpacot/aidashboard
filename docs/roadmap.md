# Roadmap

## Phase 1: Foundation and voice loop ✅ (v0.1.0)

- Monorepo, CI, docs site, ADRs, design tokens
- Core service with a hexagonal architecture and the voice state machine
- Wake word → cached greeting → listen → transcribe → stream → speak
- Reactive orb, karaoke captions, command bar
- Widget SDK, registry, built-in widgets, mobile-app placeholders
- Tauri shell

## Phase 2: Voice polish

- **Barge-in**: say the wake word, or just talk, to interrupt Jarvis mid-sentence
- Push-to-talk global hotkey (`tauri-plugin-global-shortcut`)
- UI sound design: subtle chimes for wake and end of listening
- Speaker verification, so Jarvis answers only your voice (SpeechBrain ECAPA)
- Silero VAD adapter; per-stage latency metrics in the Systems widget

## Phase 3: The brain

- LLM **tool calling** with a tool registry; widgets expose `voiceIntents` as tools
- Long-term memory: SQLite + `sqlite-vec`, with embeddings from Ollama (`nomic-embed-text`)
- Persona settings (formality, verbosity, humour)
- Web search through self-hosted SearXNG; ask questions over a local documents folder (RAG)
- MCP client support, so external tool servers plug in

## Phase 4: Dashboard

- User-editable layout: drag and resize, persisted (react-grid-layout)
- Built-in widgets: Weather (Open-Meteo), News (RSS), Calendar (ICS / Google), System monitor
- Morning briefing: spoken summary of weather, schedule, headlines and reminders
- Command palette, themes (Arctic, Stark Gold, Stealth), ambient/screensaver mode, focus mode

## Phase 5: Desktop integration

- Core service bundled as a Tauri sidecar (PyInstaller), so one installer does everything
- System tray, autostart, always-on-top mini-orb
- Notifications center

## Phase 6: Mobile apps

- Secure remote access to the core service via Tailscale
- Token auth for devices; OpenAPI-generated clients
- Replace placeholders with real Tasks, Schedule and News widgets fed by your apps
- Push notifications from apps to the dashboard

## Feature ideas backlog

Timers and alarms · unit/currency conversion · clipboard summarizer · daily voice journal · habit tracker · Home Assistant control · webcam presence greeting (MediaPipe) · offline mode indicator · multi-language support
