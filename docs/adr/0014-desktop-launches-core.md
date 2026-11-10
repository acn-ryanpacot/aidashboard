# 0014. The desktop app launches the core service

- Status: Accepted
- Date: 2026-11-10

## Context

Running Jarvis meant two terminals: the core service and the UI. The goal is "click the app, Jarvis is there". A fully frozen Python bundle (PyInstaller with PyTorch, CTranslate2, ONNX Runtime and model code) is several GB and fragile across library updates.

## Decision

On start-up, the Tauri shell:

1. does nothing if `JARVIS_CORE_AUTOSTART=0`, or if something already answers on 127.0.0.1:8765;
2. otherwise runs, in order of preference: `JARVIS_CORE_COMMAND`; a bundled `jarvis-core/` folder in the app resources; or the checkout's `services/core/.venv` Python (`python -m jarvis_core`, from `JARVIS_CORE_DIR` or the path it was compiled from);
3. hides the console window, and **kills the process on exit**, but only if it started it.

It uses the venv's Python directly rather than `uv run`, so that killing the child stops the real server rather than leaving an orphan. A PyInstaller one-folder bundle (`scripts/build-core-sidecar.ps1` plus `tauri.bundle-core.conf.json`) is provided as an **experimental** path to a self-contained installer.

## Consequences

- **+** One click starts everything. Developers who run `pnpm dev:core` themselves are unaffected, because the running core is detected.
- **+** No new Tauri plugin or permission: it's plain `std::process`.
- **−** The installed app depends on the checkout folder unless the experimental bundle is used. That's acceptable for a single personal PC, and it's documented in the setup guide.
