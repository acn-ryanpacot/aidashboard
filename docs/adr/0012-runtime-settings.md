# 0012. Live settings: environment defaults plus stored overrides

- Status: Accepted
- Date: 2026-11-10

## Context

Tuning Jarvis (wake sensitivity, end-of-speech pause, voice, model, feeds) meant editing `.env` and restarting a service that takes 10–30 s to load its models. A premium assistant should be tuned from its own UI, with immediate effect. The dashboard layout and appearance also need somewhere durable to live.

## Decision

- `RuntimeSettings` (Pydantic) lists every user-tunable value. `.env` and environment variables supply the defaults.
- `SettingsService` validates partial updates **atomically**: if any field is invalid, nothing changes. It persists only the values that differ from the defaults (in the SQLite `preferences` table) and calls registered appliers.
- The container's applier pushes changes into live components:
    - persona and greeting (re-synthesized when the name or voice changes)
    - Kokoro voice and speed
    - the Ollama model
    - voice-ID threshold
    - cache invalidation for news and calendar
    - every connected session's timing, barge-in mode and wake threshold
- Then it broadcasts `data_changed: settings`. Clients refresh what they display (name, barge-in mode).
- Settings that need a model reload or a restart (STT model, wake model, engines, ports) stay `.env`-only.
- UI documents (layout and so on) are stored under the `ui:` namespace via `/api/ui-preferences/{key}`, limited to 64 KB each. Appearance (theme, ambient timeout) stays per device in localStorage.

## Consequences

- **+** Every common tweak is instant, and "Reset to defaults" always returns to the known `.env` values.
- **+** Invalid stored values (e.g. after an upgrade) are ignored with a warning instead of preventing start-up.
- **−** Two sources of truth to explain. The Settings screen shows the effective values, and the docs mark which settings are live.
