# Getting started

## 1. Install the toolchain (all free)

| Tool                            | Why                         | Install                                                   |
| ------------------------------- | --------------------------- | --------------------------------------------------------- |
| Node.js 22+                     | UI build tooling            | <https://nodejs.org>                                      |
| pnpm                            | JS package manager          | `corepack enable` (ships with Node)                       |
| uv                              | Python + package manager    | `winget install astral-sh.uv` or see docs.astral.sh/uv    |
| Ollama                          | Runs the local LLM          | <https://ollama.com/download>                             |
| Rust (optional)                 | Native Tauri window         | <https://rustup.rs>, plus the MSVC build tools on Windows |
| espeak-ng (optional)            | Kokoro fallback for rare words | <https://github.com/espeak-ng/espeak-ng/releases>       |

!!! note "Python version"
    `services/core/.python-version` pins **Python 3.12**. uv downloads it automatically, and you don't need a system Python. The speech libraries (PyTorch, CTranslate2, ONNX Runtime) publish wheels for 3.12 first.

## 2. Install the project

```bash
pnpm install
ollama pull llama3.2:3b
ollama pull nomic-embed-text      # long-term memory & document search
cd services/core
uv sync --group dev --extra voice
```

The first `uv sync --extra voice` downloads about 2 GB (PyTorch and friends). On first start, the core service also downloads model weights into your Hugging Face cache: Whisper `base.en` (~150 MB), Kokoro (~330 MB), and the openWakeWord models (a few MB).

## 3. Run

```bash
# terminal 1, from the repository root
pnpm dev:core

# terminal 2
pnpm dev          # browser at http://localhost:5173
# or
pnpm dev:app      # native window (requires Rust)
```

Click **Engage**, allow microphone access, and say **"Hey Jarvis"**. To use the exact phrase **"Hello Jarvis"**, train a custom model as described in [Custom wake word](guides/custom-wake-word.md).

Optional extras: `--extra speaker` (voice ID, see [Voice ID](guides/voice-id.md)) and `--extra mcp` (external tool servers, see [MCP servers](guides/mcp.md)).

Try: *"Hey Jarvis"*, then *"add buy milk to my tasks"*, *"remind me to stretch in ten minutes"*, *"what's the weather in London?"*, *"remember that my passport expires in March"*. Interrupt by saying *"Hey Jarvis"* again, or press **Ctrl+Space** to talk without the wake word.

## Text-only mode (no speech stack)

Useful on a low-powered machine or for UI work:

```bash
cd services/core
uv sync --group dev
JARVIS_WAKE_ENGINE=none JARVIS_STT_ENGINE=none JARVIS_TTS_ENGINE=none JARVIS_VAD_ENGINE=energy uv run jarvis-core
```

(PowerShell: `$env:JARVIS_TTS_ENGINE='none'` and so on, or put the values in `services/core/.env`.)

## Choosing a model

`llama3.2:3b` runs acceptably on a CPU. With a GPU (8 GB+ VRAM), a 7–8B instruct model is noticeably smarter. Browse <https://ollama.com/library>, `ollama pull` your choice, and set `JARVIS_LLM_MODEL`.

## Troubleshooting

| Symptom                                    | Fix                                                                                   |
| ------------------------------------------ | ------------------------------------------------------------------------------------- |
| "Core offline" on the engage screen        | Start `pnpm dev:core`; check that port 8765 is free                                    |
| "I can't reach my language model"          | Start Ollama (`ollama serve`) and pull the configured model                           |
| Wake word never triggers                   | Lower `JARVIS_WAKE_THRESHOLD` (e.g. 0.35); check the Systems widget shows *Microphone: Live* |
| Triggers by itself                         | Raise `JARVIS_WAKE_THRESHOLD` (e.g. 0.7)                                              |
| Cuts you off mid-sentence                  | Raise `JARVIS_END_OF_SPEECH_MS` (e.g. 1200)                                           |
| Microphone "Blocked"                       | Allow mic access for the browser/WebView in Windows privacy settings                  |
| Answers are slow on first question         | Normal: models are loading. Later turns are fast                                      |
