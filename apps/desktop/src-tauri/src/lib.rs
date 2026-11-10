//! Jarvis OS desktop shell.
//!
//! Phase 1 keeps the native layer deliberately thin: it hosts the React UI in
//! a native window. Planned additions (see docs/roadmap.md):
//! - launch the Python core service as a sidecar process,
//! - a global push-to-talk hotkey (`tauri-plugin-global-shortcut`),
//! - system-tray presence and autostart (`tauri-plugin-autostart`).

/// Build and run the Tauri application.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running Jarvis OS");
}
