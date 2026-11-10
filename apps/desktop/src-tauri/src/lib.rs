//! Jarvis OS desktop shell.
//!
//! The native layer stays deliberately thin:
//! - hosts the React UI in a native window,
//! - starts the Python core service if it isn't already running, and stops
//!   it again on exit (see [`core_service`]),
//! - registers a system-wide push-to-talk shortcut (see [`shortcuts`]).

use tauri::Manager;

/// Name of the event the web view listens for (see `usePushToTalk.ts`).
pub const PUSH_TO_TALK_EVENT: &str = "push-to-talk";

/// Build and run the Tauri application.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .setup(|app| {
            let child = core_service::ensure_running(app);
            app.manage(core_service::CoreProcess::new(child));
            #[cfg(desktop)]
            shortcuts::register(app)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Jarvis OS");

    app.run(|handle, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(process) = handle.try_state::<core_service::CoreProcess>() {
                process.stop();
            }
        }
    });
}

mod core_service {
    //! Launch the core service (`jarvis-core`) alongside the window.
    //!
    //! Resolution order:
    //! 1. `JARVIS_CORE_AUTOSTART=0` → never launch (you run it yourself).
    //! 2. Something already listens on 127.0.0.1:8765 → use it, launch nothing.
    //! 3. `JARVIS_CORE_COMMAND` → run that command line through the shell.
    //! 4. A bundled build in the app's resources (`jarvis-core/jarvis-core.exe`).
    //! 5. The repository checkout: `JARVIS_CORE_DIR` or, by default, the
    //!    `services/core` folder this app was compiled from — using its
    //!    `.venv` Python directly so that stopping it stops the real process.

    use std::net::{SocketAddr, TcpStream};
    use std::path::{Path, PathBuf};
    use std::process::{Child, Command};
    use std::sync::Mutex;
    use std::time::Duration;

    const CORE_ADDR: &str = "127.0.0.1:8765";

    /// The core process we started (if any), stopped on exit.
    pub struct CoreProcess(Mutex<Option<Child>>);

    impl CoreProcess {
        pub fn new(child: Option<Child>) -> Self {
            Self(Mutex::new(child))
        }

        /// Stop the core service if this app started it.
        pub fn stop(&self) {
            if let Ok(mut guard) = self.0.lock() {
                if let Some(mut child) = guard.take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        }
    }

    fn already_running() -> bool {
        let addr: SocketAddr = CORE_ADDR.parse().expect("valid socket address");
        TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok()
    }

    fn autostart_disabled() -> bool {
        std::env::var("JARVIS_CORE_AUTOSTART")
            .map(|v| v == "0" || v.eq_ignore_ascii_case("false"))
            .unwrap_or(false)
    }

    fn venv_python(core_dir: &Path) -> Option<PathBuf> {
        let candidates = [
            core_dir.join(".venv").join("Scripts").join("python.exe"),
            core_dir.join(".venv").join("bin").join("python"),
        ];
        candidates.into_iter().find(|p| p.is_file())
    }

    fn build_command(app: &tauri::App) -> Option<Command> {
        if let Ok(line) = std::env::var("JARVIS_CORE_COMMAND") {
            let mut cmd = if cfg!(windows) {
                let mut c = Command::new("cmd");
                c.args(["/C", &line]);
                c
            } else {
                let mut c = Command::new("sh");
                c.args(["-c", &line]);
                c
            };
            cmd.env("JARVIS_LOG_JSON", "true");
            return Some(cmd);
        }

        if let Ok(resources) = app.path().resource_dir() {
            let bundled = resources.join("jarvis-core").join(if cfg!(windows) {
                "jarvis-core.exe"
            } else {
                "jarvis-core"
            });
            if bundled.is_file() {
                return Some(Command::new(bundled));
            }
        }

        let core_dir = std::env::var("JARVIS_CORE_DIR").map(PathBuf::from).unwrap_or_else(|_| {
            Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("..").join("services").join("core")
        });
        if !core_dir.is_dir() {
            eprintln!("[jarvis] core folder not found: {}", core_dir.display());
            return None;
        }
        let mut cmd = match venv_python(&core_dir) {
            Some(python) => {
                let mut c = Command::new(python);
                c.args(["-m", "jarvis_core"]);
                c
            }
            None => {
                let mut c = Command::new("uv");
                c.args(["run", "jarvis-core"]);
                c
            }
        };
        cmd.current_dir(core_dir);
        Some(cmd)
    }

    /// Start the core service unless it is already running (or disabled).
    pub fn ensure_running(app: &tauri::App) -> Option<Child> {
        if autostart_disabled() || already_running() {
            return None;
        }
        let mut cmd = build_command(app)?;
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }
        match cmd.spawn() {
            Ok(child) => {
                println!("[jarvis] started core service (pid {})", child.id());
                Some(child)
            }
            Err(error) => {
                eprintln!("[jarvis] could not start the core service: {error}");
                None
            }
        }
    }
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
