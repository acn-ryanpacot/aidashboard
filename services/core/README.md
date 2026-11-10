# jarvis-core

The Jarvis OS core service: the voice pipeline, the AI "brain", and (from Phase 4) the widget host.

```
mic frames ─▶ wake word ─▶ greeting ─▶ VAD/endpointing ─▶ STT ─▶ LLM (streamed)
                                                                    │
                       client playback ◀── WAV + word timings ◀── TTS per sentence
```

## Quick start

```bash
uv sync --group dev --extra voice   # first run downloads ~2 GB (PyTorch, models)
cp .env.example .env                # optional — every setting has a default
uv run jarvis-core                  # serves http://127.0.0.1:8765
```

Run it without the speech stack (text chat only):

```bash
uv sync --group dev
JARVIS_WAKE_ENGINE=none JARVIS_STT_ENGINE=none JARVIS_TTS_ENGINE=none JARVIS_VAD_ENGINE=energy uv run jarvis-core
```

## Layout

| Package                    | Responsibility                                                    |
| -------------------------- | ----------------------------------------------------------------- |
| `jarvis_core.domain`       | Value objects, events and **ports** (interfaces). No I/O.         |
| `jarvis_core.application`  | Use cases: `VoiceSession`, endpointing, sentence chunking, persona |
| `jarvis_core.adapters`     | Ollama, faster-whisper, Kokoro, openWakeWord, WebRTC/energy VAD    |
| `jarvis_core.api`          | FastAPI app, `/api/health`, `/ws/voice` and the wire protocol      |
| `jarvis_core.container`    | Composition root: picks an adapter for each port from `Settings`   |

## Quality gates

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest --cov=jarvis_core
```

Every test runs against in-memory fakes (`tests/fakes.py`), so the suite is fast and needs no models.

See the [documentation site](../../docs/index.md) for architecture, protocol and configuration details.
