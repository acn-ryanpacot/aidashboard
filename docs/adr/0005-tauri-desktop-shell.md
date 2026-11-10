# 0005. Tauri for the desktop shell

- Status: Accepted
- Date: 2026-11-10

## Context

The dashboard should feel like a native, always-available app (its own window, tray, hotkeys, autostart) while being built with web technology for design velocity.

## Decision

Use **Tauri 2**. The React app is a standard Vite project that also runs in a plain browser during development. Tauri adds the native window, a strict CSP, and least-privilege capabilities (`core:default` only for now).

Alternative considered: Electron. It is mature, but it ships a full Chromium (about 150 MB), uses more RAM, and has a weaker default security posture.

## Consequences

- **+** Small binaries (a few MB, using the system WebView2 on Windows), low memory, and a strong security model.
- **+** A plugin ecosystem for global shortcuts, autostart, tray and sidecar processes.
- **−** Requires the Rust toolchain to build. The UI can still be developed in the browser without it.
- **−** Behaviour depends on the system WebView. Windows uses Chromium-based WebView2, which supports everything used here (AudioWorklet, WebSockets, backdrop-filter).
