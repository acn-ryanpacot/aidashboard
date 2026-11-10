# Voice protocol (`/ws/voice`)

Version **1**. Sources of truth: `services/core/src/jarvis_core/api/protocol.py` (Pydantic) and its TypeScript mirror `apps/desktop/src/core/voice/protocol.ts`. **Change both together.**

## Transport

- One WebSocket per client = one `VoiceSession`.
- The `Origin` header must be in `JARVIS_ALLOWED_ORIGINS` or the socket is closed with code 1008. Clients that send no Origin header (CLI tools, native apps) are allowed.
- Binary frames carry audio. Text frames carry JSON objects with a `type` discriminator.

## Client → server

| Frame  | Payload                                             | Meaning                                  |
| ------ | --------------------------------------------------- | ---------------------------------------- |
| binary | 2560 bytes: 1280 samples, 16 kHz, mono, PCM16 LE    | 80 ms of microphone audio                |
| text   | `{"type":"activate"}`                               | Same as saying the wake word             |
| text   | `{"type":"text_query","text":"…"}`                  | Typed question (1–4000 chars)            |
| text   | `{"type":"playback_ended","segment_id":"seg-3"}`    | A speech segment finished playing        |
| text   | `{"type":"cancel"}`                                 | Stop and return to idle                  |

Frames of any other size are ignored. Send audio only while idle (when a wake word is enabled) or listening; the server ignores it in other states.

## Server → client

| `type`            | Fields                                                                  |
| ----------------- | ----------------------------------------------------------------------- |
| `ready`           | `protocol_version`, `assistant_name`, `user_name`, `wake_word_enabled`, `wake_model`, `speech_input_enabled`, `speech_output_enabled`, `input_sample_rate`, `input_frame_samples` |
| `state`           | `state`: `idle` \| `listening` \| `thinking` \| `speaking`              |
| `wake`            | (none)                                                                  |
| `transcript`      | `text`: what the user said                                               |
| `assistant_delta` | `text`: incremental answer text                                          |
| `speech_segment`  | `segment_id`, `kind` (`greeting`\|`answer`), `text`, `duration`, `words[]` `{word,start,end}`. **Immediately followed by one binary frame containing a WAV file.** |
| `turn_complete`   | `text`: the full answer                                                  |
| `error`           | `message`: safe to show the user                                         |

## Example exchange

```text
← {"type":"ready","protocol_version":1,"user_name":"Ryan",…}
← {"type":"state","state":"idle"}
→ {"type":"text_query","text":"Status report"}
← {"type":"state","state":"thinking"}
← {"type":"transcript","text":"Status report"}
← {"type":"assistant_delta","text":"All systems"}
← {"type":"assistant_delta","text":" are nominal, Ryan."}
← {"type":"state","state":"speaking"}
← {"type":"speech_segment","segment_id":"seg-1","kind":"answer","text":"All systems are nominal, Ryan.","duration":2.1,"words":[…]}
← <binary WAV>
← {"type":"turn_complete","text":"All systems are nominal, Ryan."}
→ {"type":"playback_ended","segment_id":"seg-1"}
← {"type":"state","state":"listening"}
```

## Compatibility rules

- Clients **must ignore unknown message types** (`parseServerMessage` returns `null`).
- Adding optional fields or new message types is a minor change. Removing or renaming anything requires bumping `PROTOCOL_VERSION`.
