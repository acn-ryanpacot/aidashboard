# Voice protocol (`/ws/voice`)

Version **3**. Sources of truth: `services/core/src/jarvis_core/api/protocol.py` (Pydantic) and its TypeScript mirror `apps/desktop/src/core/voice/protocol.ts`. **Change both together.**

## Transport

- One WebSocket per client = one `VoiceSession`.
- The `Origin` header must be in `JARVIS_ALLOWED_ORIGINS` or the socket is closed with code 1008. Clients without an Origin header (CLI tools, native apps) are allowed.
- Binary frames carry audio. Text frames carry JSON objects with a `type` discriminator.

## Client → server

| Frame  | Payload                                            | Meaning                                       |
| ------ | -------------------------------------------------- | --------------------------------------------- |
| binary | 2560 bytes: 1280 samples, 16 kHz, mono, PCM16 LE   | 80 ms of microphone audio                     |
| text   | `{"type":"activate"}`                              | Same as the wake word: greet, then listen     |
| text   | `{"type":"listen"}`                                | Push-to-talk: listen now, no greeting         |
| text   | `{"type":"text_query","text":"…"}`                 | Typed question (1–4000 chars)                 |
| text   | `{"type":"playback_ended","segment_id":"seg-3"}`   | A speech segment finished playing             |
| text   | `{"type":"cancel"}`                                | Stop (also cancels enrollment)                |
| text   | `{"type":"barge_in"}`                              | The client's echo-aware detector heard the user talk over Jarvis (`voice` mode) |
| text   | `{"type":"enroll_voice"}`                          | Start voice-ID enrollment                     |

When to send audio (`wantsAudio()` in the UI):

- while **idle**, if a wake word is enabled;
- always while **listening**;
- while **thinking/speaking**, if barge-in is enabled.

## Server → client

| `type`             | Fields                                                                           |
| ------------------ | -------------------------------------------------------------------------------- |
| `ready`            | `protocol_version`, `assistant_name`, `user_name`, `wake_word_enabled`, `wake_model`, `speech_input_enabled`, `speech_output_enabled`, `barge_in`, `barge_in_min_speech_ms`, `speaker_verification_enabled`, `speaker_enrolled`, `tools[]`, `input_sample_rate`, `input_frame_samples` |
| `state`            | `state`: `idle` \| `listening` \| `thinking` \| `speaking`                       |
| `wake`             | (none)                                                                           |
| `interrupted`      | (none). **Stop playback immediately**                                            |
| `transcript`       | `text`: what the user said                                                        |
| `assistant_delta`  | `text`: incremental answer text                                                   |
| `tool`             | `name`, `label` (e.g. "Checking the weather")                                    |
| `speech_segment`   | `segment_id`, `kind` (`greeting`\|`answer`\|`announcement`), `text`, `duration`, `words[]`. **Followed by one binary WAV frame** |
| `turn_complete`    | `text`: the full answer                                                           |
| `metrics`          | `stt_ms`, `first_token_ms`, `first_audio_ms`, `total_ms`, `tools[]`              |
| `speaker_rejected` | `score`: similarity of the ignored voice                                         |
| `enrollment`       | `status` (`recording`\|`complete`\|`cancelled`\|`failed`), `collected`, `required` |
| `notification`     | `kind` (e.g. `reminder`), `text`                                                 |
| `data_changed`     | `topic` (`tasks`, `reminders`, `memories`, `voiceprint`, `settings`, `ui:<key>`)                         |
| `error`            | `message`: safe to show the user                                                 |

## Example: a tool-using turn

```text
→ {"type":"text_query","text":"add buy milk to my list"}
← {"type":"state","state":"thinking"}
← {"type":"transcript","text":"add buy milk to my list"}
← {"type":"tool","name":"add_task","label":"Updating your tasks"}
← {"type":"data_changed","topic":"tasks"}
← {"type":"assistant_delta","text":"Done, sir."}
← {"type":"state","state":"speaking"}
← {"type":"speech_segment","segment_id":"seg-1","kind":"answer",…}
← <binary WAV>
← {"type":"turn_complete","text":"Done, sir."}
← {"type":"metrics","stt_ms":null,"first_token_ms":812.4,…,"tools":["add_task"]}
→ {"type":"playback_ended","segment_id":"seg-1"}
← {"type":"state","state":"listening"}
```

## REST endpoints

| Method & path              | Purpose                                  |
| -------------------------- | ---------------------------------------- |
| `GET /api/health`          | Status and capabilities                  |
| `GET/POST /api/tasks`      | List (`?include_done=true`) and create tasks |
| `PATCH/DELETE /api/tasks/{id}` | Complete/reopen (`{"done":true}`) and delete |
| `GET/POST /api/reminders`  | Upcoming reminders; create (`due_at` must have a timezone) |
| `DELETE /api/reminders/{id}` | Cancel                                 |
| `GET /api/memories`        | Audit long-term memory                   |
| `DELETE /api/memories/{id}` | Forget                                  |
| `DELETE /api/voiceprint`   | Remove the enrolled voice                |
| `GET/PUT /api/settings`, `POST /api/settings/reset` | Live settings (values + defaults) |
| `GET /api/voices`, `GET /api/models` | Choices for Settings |
| `GET/PUT /api/ui-preferences/{key}` | UI documents, e.g. the dashboard `layout` |
| `GET /api/weather?location=` | Current weather (home location by default) |
| `GET /api/news?limit=` | Headlines from the configured feeds |
| `GET /api/calendar?days=` | Upcoming events (`configured: false` if none connected) |
| `GET /api/system` | CPU, RAM, GPU load |

Interactive OpenAPI docs: <http://127.0.0.1:8765/docs>. Every mutation broadcasts `data_changed` to all WebSocket clients.

## Compatibility rules

- Clients **must ignore unknown message types**.
- Adding optional fields or new message types is a minor change. Removing or renaming anything requires bumping `PROTOCOL_VERSION`.
- v2 → v3: added the `barge_in` client message and `ready.barge_in_min_speech_ms`.
- v1 → v2: added `listen`, `enroll_voice`, `interrupted`, `tool`, `metrics`, `speaker_rejected`, `enrollment`, `notification`, `data_changed`, the `announcement` segment kind and new `ready` fields.
