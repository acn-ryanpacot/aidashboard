# Swapping an AI component (writing an adapter)

Every engine sits behind a **port** in `jarvis_core/domain/ports.py`:

| Port                    | Default adapter                  | Ideas                                       |
| ----------------------- | -------------------------------- | ------------------------------------------- |
| `LanguageModel`         | `OllamaLanguageModel`            | llama.cpp server, LM Studio, a cloud API    |
| `SpeechToText`          | `FasterWhisperSpeechToText`      | whisper.cpp, Vosk                           |
| `TextToSpeech`          | `KokoroTextToSpeech`             | Piper, XTTS                                 |
| `WakeWordDetector`      | `OpenWakeWordDetector`           | Porcupine                                   |
| `VoiceActivityDetector` | `WebRtcVoiceActivityDetector`    | Silero VAD                                  |

## Example: an OpenAI-compatible LLM server

Many local servers (llama.cpp, LM Studio, vLLM) speak the OpenAI chat API.

```python
# jarvis_core/adapters/llm/openai_compatible.py
"""LLM adapter for any OpenAI-compatible /v1/chat/completions server."""

class OpenAICompatibleLanguageModel:
    """Implements :class:`~jarvis_core.domain.ports.LanguageModel`."""

    def __init__(self, *, base_url: str, model: str) -> None: ...

    async def stream_chat(self, messages):
        # POST /v1/chat/completions with stream=true, parse "data:" SSE lines,
        # yield choices[0].delta.content; raise LanguageModelError on failure.
        ...
```

Then:

1. Add a setting, e.g. `llm_engine: Literal["ollama", "openai_compatible"]`, in `config.py`.
2. Branch on it in `container._build_llm`, importing the adapter lazily.
3. Write tests against `httpx.MockTransport`, as `tests/test_adapters.py` does for Ollama.
4. Document the new settings in `docs/configuration.md`.

## Rules

- Adapters translate vendor exceptions into domain errors (`LanguageModelError`, `SpeechError`, `ConfigurationError`). Never let an `httpx` or `torch` error escape into the application layer.
- Import heavy SDKs **inside** the constructor, so the service still starts without them.
- Blocking adapters (STT, TTS) stay synchronous; `VoiceSession` runs them in worker threads.
- Implement `warm_up()` / `aclose()` if the engine benefits from preloading or holds connections. The container detects them through the `SupportsWarmUp` and `SupportsClose` protocols.
