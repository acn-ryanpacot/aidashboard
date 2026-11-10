//! Jarvis OS desktop shell.
//!
//! The native layer stays deliberately thin: it hosts the React UI in a
//! native window and registers a system-wide push-to-talk shortcut.
//! Planned additions (see docs/roadmap.md):
//! - launch the Python core service as a sidecar process,
//! - system-tray presence and autostart (`tauri-plugin-autostart`).

/// Name of the event the web view listens for (see `usePushToTalk.ts`).
pub const PUSH_TO_TALK_EVENT: &str = "push-to-talk";

/// Build and run the Tauri application.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            #[cfg(desktop)]
            shortcuts::register(app)?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Jarvis OS");
}

#[cfg(desktop)]
mod shortcuts {
    use tauri::{App, Emitter};
    use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

    /// Ctrl + Shift + Space anywhere in the OS → start listening.
    ///
    /// (Inside the window, Ctrl + Space is handled by the web view itself.)
    pub fn register(app: &mut App) -> Result<(), Box<dyn std::error::Error>> {
        let push_to_talk = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::Space);
        app.handle().plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |app, shortcut, event| {
                    if shortcut == &push_to_talk && event.state() == ShortcutState::Pressed {
                        let _ = app.emit(super::PUSH_TO_TALK_EVENT, ());
                    }
                })
                .build(),
        )?;
        app.global_shortcut().register(push_to_talk)?;
        Ok(())
    }
}
