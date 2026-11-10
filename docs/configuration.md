# Configuration

## Core service

Settings are read from environment variables prefixed with `JARVIS_`, or from `services/core/.env` (start from `.env.example`). They are validated at startup by `jarvis_core.config.Settings`.

### Server

| Variable                | Default       | Notes                                                       |
| ----------------------- | ------------- | ----------------------------------------------------------- |
| `JARVIS_HOST`           | `127.0.0.1`   | Keep on loopback unless you add authentication              |
| `JARVIS_PORT`           | `8765`        |                                                             |
| `JARVIS_LOG_LEVEL`      | `INFO`        | `DEBUG` shows per-turn details                              |
| `JARVIS_LOG_JSON`       | `false`       | One JSON object per line                                    |
| `JARVIS_ALLOWED_ORIGINS`| Vite + Tauri  | JSON list of origins allowed to open the WebSocket          |

### Persona

| Variable                   | Default                            |
| -------------------------- | ---------------------------------- |
| `JARVIS_USER_NAME`         | `Ryan`                             |
| `JARVIS_ASSISTANT_NAME`    | `Jarvis`                           |
| `JARVIS_GREETING_TEMPLATE` | `How can I help you {user_name}?`  |

### Wake word and listening

| Variable                   | Default        | Notes                                                    |
| -------------------------- | -------------- | -------------------------------------------------------- |
| `JARVIS_WAKE_ENGINE`       | `openwakeword` | `none` = activate by clicking the core only              |
| `JARVIS_WAKE_MODEL`        | `hey_jarvis`   | Pretrained name or path to your `.onnx`                  |
| `JARVIS_WAKE_THRESHOLD`    | `0.5`          | Higher = fewer false triggers                            |
| `JARVIS_VAD_ENGINE`        | `webrtc`       | `energy` needs no extra dependency                       |
| `JARVIS_VAD_AGGRESSIVENESS`| `2`            | 0–3                                                      |
| `JARVIS_END_OF_SPEECH_MS`  | `800`          | Silence that ends your turn                              |
| `JARVIS_LISTEN_TIMEOUT_MS` | `6000`         | Give up if you say nothing after the greeting            |
| `JARVIS_FOLLOW_UP_MS`      | `6000`         | Keep listening after an answer; `0` disables             |
| `JARVIS_MAX_UTTERANCE_MS`  | `15000`        | Hard cap per request                                     |
| `JARVIS_BARGE_IN`          | `wake_word`    | `voice` = just talk over Jarvis; `off`                   |
| `JARVIS_BARGE_IN_MIN_SPEECH_MS` | `400`     | Continuous speech needed for `voice` barge-in            |
| `JARVIS_PLAYBACK_GRACE_MS` | `4000`         | Watchdog slack for unacknowledged audio                  |

`JARVIS_VAD_ENGINE` also accepts `silero` (neural, best in noisy rooms).

### Voice ID

| Variable                            | Default | Notes                                        |
| ----------------------------------- | ------- | -------------------------------------------- |
| `JARVIS_SPEAKER_VERIFICATION`       | `false` | Requires `uv sync --extra voice --extra speaker` |
| `JARVIS_SPEAKER_THRESHOLD`          | `0.30`  | Cosine similarity needed to accept a voice   |
| `JARVIS_SPEAKER_ENROLLMENT_SAMPLES` | `3`     | Utterances recorded when enrolling           |

### Speech-to-text

| Variable                  | Default          | Notes                                       |
| ------------------------- | ---------------- | ------------------------------------------- |
| `JARVIS_STT_ENGINE`       | `faster_whisper` | `none` = typed questions only               |
| `JARVIS_STT_MODEL`        | `base.en`        | `tiny.en` (fastest) … `small.en` (better)   |
| `JARVIS_STT_DEVICE`       | `auto`           | `cpu`, `cuda`                               |
| `JARVIS_STT_COMPUTE_TYPE` | `int8`           | `float16` on GPU                            |

### Language model

| Variable                 | Default                   |
| ------------------------ | ------------------------- |
| `JARVIS_LLM_BASE_URL`    | `http://127.0.0.1:11434`  |
| `JARVIS_LLM_MODEL`       | `llama3.2:3b`             |
| `JARVIS_LLM_TEMPERATURE` | `0.6`                     |
| `JARVIS_LLM_TIMEOUT_S`   | `120`                     |
| `JARVIS_HISTORY_MESSAGES`| `20`                      |

### Brain: tools, memory and knowledge

| Variable                       | Default            | Notes                                              |
| ------------------------------ | ------------------ | -------------------------------------------------- |
| `JARVIS_TOOLS_ENABLED`         | `true`             | `false` = plain chat                               |
| `JARVIS_MAX_TOOL_ROUNDS`       | `4`                | Model-tool round trips per turn                    |
| `JARVIS_TOOL_ROUTING`          | `auto`             | `auto` = attach only relevant tools (fast on CPU); `all` |
| `JARVIS_TOOL_ROUTING_MAX_TOOLS`| `6`                | Cap on tools attached to one request               |
| `JARVIS_MEMORY_ENABLED`        | `true`             | Long-term memory                                   |
| `JARVIS_EMBEDDING_MODEL`       | `nomic-embed-text` | `ollama pull` it; keyword fallback if missing      |
| `JARVIS_MEMORY_MIN_SCORE`      | `0.5`              | Similarity for a memory to count as relevant       |
| `JARVIS_MEMORY_TOP_K`          | `3`                | Memories added to each prompt                      |
| `JARVIS_WEATHER_ENABLED`       | `true`             | Open-Meteo                                         |
| `JARVIS_DEFAULT_LOCATION`      | (empty)            | e.g. `Manila`, used when no place is named          |
| `JARVIS_ENCYCLOPEDIA_ENABLED`  | `true`             | Wikipedia                                          |
| `JARVIS_ENCYCLOPEDIA_USER_AGENT` | `JarvisOS/0.2 (+https://localhost; …)` | Wikimedia's robot policy wants a contact URL or email here; put your own repo URL if you have one |
| `JARVIS_SEARXNG_URL`           | (empty)            | Enables `web_search`                               |
| `JARVIS_DOCUMENTS_DIR`         | (empty)            | Enables `search_documents` over that folder         |
| `JARVIS_MCP_SERVERS`           | `[]`               | JSON list, see the MCP guide                       |
| `JARVIS_REMINDER_POLL_S`       | `5`                | Reminder check interval                            |
| `JARVIS_PERSONA_FORMALITY`     | `balanced`         | `formal`, `balanced` or `casual`                   |
| `JARVIS_PERSONA_VERBOSITY`     | `balanced`         | `brief`, `balanced` or `detailed`                  |
| `JARVIS_PERSONA_HUMOUR`        | `dry`              | `none`, `dry` or `playful`                         |

### Storage

| Variable          | Default         | Notes                                              |
| ----------------- | --------------- | -------------------------------------------------- |
| `JARVIS_DATA_DIR` | `~/.jarvis-os`  | `jarvis.db`, `voiceprint.json`, model caches       |

### Text-to-speech

| Variable               | Default     | Notes                                                    |
| ---------------------- | ----------- | -------------------------------------------------------- |
| `JARVIS_TTS_ENGINE`    | `kokoro`    | `none` = text replies only                               |
| `JARVIS_TTS_LANG_CODE` | `b`         | `a` American, `b` British English                        |
| `JARVIS_TTS_VOICE`     | `bm_george` | Also try `bm_lewis`, `bm_daniel`, `am_michael`           |
| `JARVIS_TTS_SPEED`     | `1.0`       |                                                          |

## Desktop UI

Vite env vars, set in `apps/desktop/.env.local`:

| Variable                | Default                  |
| ----------------------- | ------------------------ |
| `VITE_JARVIS_CORE_URL`  | `http://127.0.0.1:8765`  |
| `VITE_JARVIS_USER_NAME` | `Ryan` (until connected) |

If you change the core URL, also update `connect-src` in `apps/desktop/src-tauri/tauri.conf.json`.
