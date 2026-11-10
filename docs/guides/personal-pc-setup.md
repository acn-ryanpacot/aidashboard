# Setting up Jarvis OS on your personal PC (Windows 11 + NVIDIA GPU)

This guide takes a fresh Windows 11 PC with an NVIDIA graphics card to a fully working Jarvis: wake word, GPU speech recognition, the British voice, tools, voice ID and the native desktop app.

- **Time:** about 1–2 hours. Most of it is downloads.
- **Disk:** about 20 GB (toolchains ~6 GB, Python packages ~6 GB, models 5–20 GB depending on the LLM).
- **Commands:** run them in **PowerShell**. Where it says *as Administrator*, right-click **Terminal** and choose **Run as administrator**.

!!! tip "Work through it in order"
    Every step ends with a check. If a check fails, fix it before moving on. Step 8 (`jarvis-doctor`) tests everything in one go.

---

## 1. Move the project to the PC

You don't need to copy `node_modules` or `.venv`; they are rebuilt on the new PC. Pick **one** option.

### Option A: Git bundle on a USB stick (no account needed)

On the **current** laptop, in the project folder:

```powershell
git bundle create jarvis-os.bundle --all
```

Copy `jarvis-os.bundle` to the PC. Once Git is installed there (step 2), clone it:

```powershell
git clone C:\path\to\jarvis-os.bundle C:\dev\jarvis-os
```

### Option B: A private GitHub repository

Create an empty **private** repository on github.com, then on the current laptop:

```powershell
git remote add origin https://github.com/<you>/jarvis-os.git
git push -u origin master
```

On the PC: `git clone https://github.com/<you>/jarvis-os.git C:\dev\jarvis-os`.

!!! note
    Use a path **without spaces**, such as `C:\dev\jarvis-os`. Some build tools still trip over spaces. If you're moving the project off a work laptop, check your employer's policy on personal projects and on pushing code to personal accounts.

**Check:** `C:\dev\jarvis-os\README.md` exists.

---

## 2. Install the toolchain

### 2.0 Turn off Smart App Control

Windows 11's **Smart App Control** blocks unsigned programs that Microsoft hasn't seen before. A development setup runs many of them:

- the Python that uv downloads;
- the launchers uv creates, such as `jarvis-doctor.exe`;
- the build programs Rust compiles while building the app.

If Smart App Control is on, `uv run …` fails with *"Failed to query Python interpreter … An Application Control policy has blocked this file"*.

**Check** its state in PowerShell:

```powershell
(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy').VerifiedAndReputablePolicyState
```

- `0` means it's off, so there's nothing to do.
- `1` means it's on.
- `2` means evaluation mode, which Windows can switch to on later.

To turn it off, open **Windows Security**, go to **App & browser control → Smart App Control settings**, and choose **Off**. Microsoft Defender antivirus keeps protecting the PC.

!!! warning
    On many Windows 11 builds you can turn Smart App Control back on only by resetting Windows. That is a fair trade for a development PC, but decide before you click.

!!! note "Work or school PCs"
    If the PC is managed by an organisation, the same message comes from its *App Control for Business* (WDAC) or AppLocker policy instead. You can't change that policy yourself; ask IT to allow the folders listed above.

### 2.1 NVIDIA driver

Install the latest **Game Ready** or **Studio** driver, either from <https://www.nvidia.com/Download/index.aspx> or through the **NVIDIA App**, then reboot.

**Check:**

```powershell
nvidia-smi
```

This should show your GPU, the driver version, and a *CUDA Version* of 12.8 or higher. You don't need to install the CUDA Toolkit separately: PyTorch brings its own CUDA libraries.

### 2.2 Developer tools (winget)

As **Administrator**:

```powershell
winget install --id Git.Git -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id astral-sh.uv -e
winget install --id Ollama.Ollama -e
winget install --id Rustlang.Rustup -e
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

| Tool                 | Why                                                         |
| -------------------- | ----------------------------------------------------------- |
| Git                  | Get and update the code                                     |
| Node.js LTS (22+)    | Builds the dashboard                                        |
| uv                   | Installs Python 3.12 and every Python package               |
| Ollama               | Runs the language model on your GPU                         |
| Rustup + VS C++ tools | Builds the native Tauri window (WebView2 ships with Windows 11) |

Optional extras:

```powershell
winget install --id eSpeak-NG.eSpeak-NG -e      # better pronunciation of rare words (Kokoro fallback)
winget install --id Docker.DockerDesktop -e     # only if you want private web search (SearXNG)
```

**Close every terminal and open a new one** so the new `PATH` takes effect. Then install pnpm (a normal terminal is fine; you don't need Administrator):

```powershell
npm install -g pnpm@10.34.9
```

If `pnpm` is still "not recognized" afterwards, close every terminal again and open a new one. (`corepack enable` is an alternative, but it needs an Administrator terminal, and Node 25+ no longer includes corepack.)

**Check:** each of these prints a version:

```powershell
git --version; node --version; pnpm --version; uv --version; ollama --version; rustc --version; cargo --version
```

---

## 3. Pull the AI models

Ollama starts automatically (there's a llama icon in the system tray). Choose a language model that fits your GPU memory. It must support **tools**; models on <https://ollama.com/library> that do are tagged *tools*.

| GPU memory (VRAM) | Suggested model (examples, check the library for newer ones) | Pull command |
| --- | --- | --- |
| 6–8 GB   | Qwen 2.5 7B / Llama 3.1 8B | `ollama pull qwen2.5:7b` |
| 10–16 GB | Qwen 2.5 14B               | `ollama pull qwen2.5:14b` |
| 24 GB+   | Qwen 2.5 32B               | `ollama pull qwen2.5:32b` |

Then pull the embedding model, which powers memory, document search and smarter tool routing:

```powershell
ollama pull nomic-embed-text
```

Leave about 2–3 GB of VRAM free for Whisper and Kokoro. On an 8 GB card, use a 7–8B model.

!!! note "Reasoning models"
    Some newer models "think" before answering, which is slower to speak. Jarvis hides `<think>` text automatically. To skip thinking altogether, set `JARVIS_LLM_THINK=false` in step 6.

**Check:**

```powershell
ollama run qwen2.5:7b "Say hello in five words"
```

This should answer within a second or two, and `nvidia-smi` should show the model using GPU memory.

---

## 4. Install the dashboard's packages

```powershell
cd C:\dev\jarvis-os
pnpm install
```

**Check:** it ends with `Done`. Warnings about ignored build scripts are fine.

---

## 5. Install the core service (GPU build)

```powershell
cd C:\dev\jarvis-os\services\core
uv sync --group dev --extra voice --extra speaker --extra cu128
```

- `voice` installs the wake word, Whisper, Kokoro, and the WebRTC and Silero voice detectors.
- `speaker` installs voice ID (SpeechBrain).
- `cu128` installs the **CUDA build of PyTorch**. It's about 3 GB, so the first sync takes a while. Use `--extra cpu` on a machine without an NVIDIA GPU. Never use both.
- Add `--extra mcp` if you want external tool servers ([MCP guide](mcp.md)).

**Check:** PyTorch sees the GPU.

```powershell
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

Expected output is something like `2.x.x+cu128 True NVIDIA GeForce RTX …`. If it prints `False`, update the NVIDIA driver and reboot.

---

## 6. Configure

```powershell
cd C:\dev\jarvis-os\services\core
Copy-Item .env.example .env
notepad .env
```

Recommended values for a GPU PC. Change only these and leave the rest:

```dotenv
# Your name & the model you pulled in step 3
JARVIS_USER_NAME=Ryan
JARVIS_LLM_MODEL=qwen2.5:7b

# Speech recognition on the GPU: small.en is accurate and fast; medium.en if you have ≥ 12 GB VRAM
JARVIS_STT_MODEL=small.en
JARVIS_STT_DEVICE=cuda
JARVIS_STT_COMPUTE_TYPE=float16

# Neural voice detection: best at ignoring keyboards, fans and TV
JARVIS_VAD_ENGINE=silero

# Weather & briefing location
JARVIS_DEFAULT_LOCATION=Manila

# Only answer your voice (enroll in step 10)
JARVIS_SPEAKER_VERIFICATION=true
```

Kokoro and voice ID use the GPU automatically when PyTorch can see it. You can change most other settings later from the dashboard's **Settings** screen, without restarting. See the [Configuration reference](../configuration.md).

---

## 7. (Optional) The exact phrase "Hello Jarvis"

The bundled wake word is "**Hey** Jarvis". To use "**Hello** Jarvis", follow [Custom wake word](custom-wake-word.md). It's a free one-hour Colab training run, after which you set `JARVIS_WAKE_MODEL=models/hello_jarvis.onnx`. You can do this later; everything else works with "Hey Jarvis".

---

## 8. Run the doctor

```powershell
cd C:\dev\jarvis-os\services\core
uv run jarvis-doctor
```

It checks Python, the data folder, the port, Ollama and both models, every speech package, the NVIDIA driver, PyTorch CUDA, Whisper's GPU support, and espeak-ng. Each line is ✓ (ok), ! (optional or degraded) or ✗ (must fix), with a fix hint (→). A healthy GPU setup looks like:

```text
  ✓ Python           3.12.x
  ✓ Ollama           3 model(s) installed
  ✓ LLM model        qwen2.5:7b
  ✓ Embedding model  nomic-embed-text
  ✓ faster-whisper (STT)  installed
  …
  ✓ NVIDIA driver    NVIDIA GeForce RTX 4070 (12 GB)
  ✓ PyTorch          2.x+cu128 · CUDA · NVIDIA GeForce RTX 4070
  ✓ Whisper GPU      1 CUDA device(s)
```

If **Whisper GPU** shows `CPU only`, see [Whisper on the GPU](#whisper-on-the-gpu) below. You can also simply set `JARVIS_STT_DEVICE=cpu`, because Whisper `small.en` is fast enough on a modern CPU.

---

## 9. First run

Open two terminals:

```powershell
# Terminal 1 — the core service (first start downloads ~1 GB of speech models)
cd C:\dev\jarvis-os
pnpm dev:core
```

Wait for `jarvis_online` and `brain_ready` in the log.

```powershell
# Terminal 2 — the native window (first build compiles Rust: ~5–10 minutes, then seconds)
cd C:\dev\jarvis-os
pnpm dev:app
```

You can also run `pnpm dev` and open <http://localhost:5173> in Edge or Chrome.

Click **Engage**, allow the microphone, and say **"Hey Jarvis"**.

!!! tip
    Once you use the native window (`pnpm dev:app`, or the installed app from step 11), you can skip terminal 1. The app starts the core service itself if it isn't already running.

---

## 10. Smoke test: everything should work

| # | Do this | You should see / hear |
| --- | --- | --- |
| 1 | Say "Hey Jarvis" | A soft chime, then "How can I help you Ryan?". The core turns mint while listening |
| 2 | "What's the weather like?" | *Checking the weather…*, then a spoken answer in a couple of seconds |
| 3 | "Add buy milk to my tasks" | The **Tasks** widget updates by itself |
| 4 | "Remind me to stretch in two minutes" | Two minutes later: "Pardon the interruption, Ryan…" |
| 5 | Ask something long, then say "Hey Jarvis" mid-answer | Jarvis stops and listens (barge-in) |
| 6 | Press **Ctrl+Space** | Jarvis listens without the greeting (push-to-talk) |
| 7 | Focus another app and press **Ctrl+Shift+Space** | Same, system-wide (native window only) |
| 8 | **Settings → Listening → Train my voice** and read three sentences | "Voiceprint saved". Others' voices are now ignored |
| 9 | **Ctrl+K → "Morning briefing"** | A spoken summary of your day |
| 10 | Click the layout icon in the top bar, then drag a widget to the other side | The layout is saved and survives restarts |
| 11 | **Settings → Appearance → Stark Gold** | The whole HUD, orb included, changes colour |

The **Systems** widget (add it with **Edit layout → Add widget**) shows the latency of every turn. On a mid-range GPU, expect roughly 1–2 s from the end of your sentence to Jarvis's first word, or 2–4 s when a tool is used.

---

## 11. Build and install the desktop app

```powershell
cd C:\dev\jarvis-os
pnpm --filter @jarvis/desktop tauri build
```

The installers are written to `apps\desktop\src-tauri\target\release\bundle\`, as `nsis\Jarvis OS_0.3.0_x64-setup.exe` and an `.msi`. Install one and launch **Jarvis OS** from the Start menu.

When the installed app starts, it launches the core service from the folder it was built from (`C:\dev\jarvis-os\services\core`) using that folder's `.venv`. It stops the core again when you close the app. To control this, set Windows user environment variables (**Settings → System → About → Advanced system settings → Environment Variables**):

| Variable | Effect |
| --- | --- |
| `JARVIS_CORE_DIR` | Use a different checkout (e.g. after moving the folder) |
| `JARVIS_CORE_COMMAND` | Run exactly this command instead |
| `JARVIS_CORE_AUTOSTART=0` | Never launch it (you run `pnpm dev:core` yourself) |

!!! note "Experimental: fully self-contained installer"
    `scripts\build-core-sidecar.ps1` bundles the core with PyInstaller. You then build with `pnpm --filter @jarvis/desktop tauri build --config src-tauri/tauri.bundle-core.conf.json`. The result needs no Python on the target PC but is several GB, and it is untested. For a single personal PC, the default above is simpler.

### Start with Windows

Press **Win+R**, type `shell:startup`, and drop a shortcut to **Jarvis OS** into that folder. Jarvis then starts, launches its core, and waits in ambient mode.

---

## Whisper on the GPU

faster-whisper uses CTranslate2, which needs NVIDIA's cuBLAS and cuDNN 9 libraries for CUDA 12. Jarvis loads the copies bundled with PyTorch automatically. If `jarvis-doctor` still reports `CPU only`, or the log shows `Could not locate cudnn_ops64_9.dll`:

1. Make sure step 5 used `--extra cu128` and its check printed `True`.
2. If it still fails, install the [CUDA Toolkit 12.x](https://developer.nvidia.com/cuda-downloads) and [cuDNN 9 for CUDA 12](https://developer.nvidia.com/cudnn-downloads), and add their `bin` folders to `PATH`.
3. Or set `JARVIS_STT_DEVICE=cpu`. The LLM and Kokoro still use the GPU, and `small.en` on a CPU adds only a few hundred milliseconds.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| *"Failed to query Python interpreter … An Application Control policy has blocked this file"* | Smart App Control is on. Turn it off (step 2.0), then rerun `uv sync` from step 5 |
| `jarvis-doctor` ✗ **Ollama unreachable** | Start Ollama from the Start menu; check `ollama list` |
| ✗ **LLM model missing** | `ollama pull <model>`, or pick an installed one in **Settings → Brain** |
| PyTorch says `False` / `+cpu` | Rerun step 5 with `--extra cu128`; update the driver and reboot |
| Out of GPU memory / very slow answers | Use a smaller model (`qwen2.5:7b`), `JARVIS_STT_MODEL=base.en`, close games and other GPU apps |
| Wake word never triggers | **Settings → Listening → Wake-word sensitivity** higher; check Windows **Privacy → Microphone** allows desktop apps |
| Triggers by itself | Lower the sensitivity; consider the custom "Hello Jarvis" model |
| Cuts you off mid-sentence | **Settings → Listening → Pause that ends your turn** to about 1200 ms |
| Jarvis interrupts itself (voice barge-in) | Use **Interrupting Jarvis → Say the wake word again**, or a headset; raise *Talk-over needed* |
| Voice ID ignores you | **Settings → Voice ID strictness** lower, or **Re-train my voice** in your usual spot |
| `pnpm dev:app` fails with a linker error | The Visual Studio Build Tools (C++ workload) are missing; rerun the last winget line in 2.2 |
| Port 8765 already in use | Another core is running (fine), or set `JARVIS_PORT` and `VITE_JARVIS_CORE_URL` to match |
| Calendar shows nothing | Paste the **secret ICS address** (not the public link) in **Settings → Briefing & feeds** |

Logs: the core prints everything to its terminal. Set `JARVIS_LOG_LEVEL=DEBUG` to see per-turn routing and timing.

---

## Keeping it up to date

```powershell
cd C:\dev\jarvis-os
git pull
pnpm install
cd services\core
uv sync --group dev --extra voice --extra speaker --extra cu128
uv run jarvis-doctor
```

Your data lives outside the repository, in `%USERPROFILE%\.jarvis-os`: tasks, reminders, memories, layout, settings and voiceprint. Back up that folder to keep everything.
