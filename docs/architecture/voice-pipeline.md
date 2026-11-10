# Voice pipeline

## The conversation loop

```mermaid
sequenceDiagram
    autonumber
    participant Mic as Mic (AudioWorklet)
    participant UI as Desktop UI
    participant Core as VoiceSession
    participant LLM as Ollama
    participant TTS as Kokoro

    loop every 80 ms
        Mic->>UI: 1280 × PCM16 @ 16 kHz
        UI->>Core: binary frame
    end
    Core->>Core: openWakeWord ≥ threshold
    Core-->>UI: wake, state=speaking
    Core-->>UI: speech_segment(greeting) + WAV (cached)
    UI->>UI: play · orb reacts · captions
    UI->>Core: playback_ended
    Core-->>UI: state=listening
    Mic->>Core: frames… then 800 ms of silence
    Core-->>UI: state=thinking
    Core->>Core: faster-whisper → "what's the time in Tokyo?"
    Core-->>UI: transcript
    Core->>LLM: stream chat
    LLM-->>Core: deltas…
    Core-->>UI: assistant_delta…
    Core->>TTS: sentence 1 (as soon as it's complete)
    TTS-->>Core: audio + word timings
    Core-->>UI: speech_segment + WAV, state=speaking
    Note over Core,TTS: sentence 2 synthesizes while 1 plays
    UI->>Core: playback_ended (each)
    Core-->>UI: turn_complete
    Core-->>UI: state=listening (follow-up) → idle
```

## State machine

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Speaking: wake word / activate
    Speaking --> Listening: greeting playback_ended
    Listening --> Thinking: end of speech
    Listening --> Idle: no speech (timeout)
    Idle --> Thinking: text_query
    Listening --> Thinking: text_query
    Thinking --> Speaking: first sentence ready
    Thinking --> Idle: error / empty transcript
    Speaking --> Listening: last playback_ended (follow-up on)
    Speaking --> Idle: last playback_ended (follow-up off)
    Speaking --> Idle: cancel
    Thinking --> Idle: cancel
```

Implemented in `jarvis_core.application.voice_session.VoiceSession`.

## Design choices

**The greeting is cached, never generated.** `GreetingCache` synthesizes "How can I help you Ryan?" once at startup. It is guaranteed verbatim and plays in under 300 ms.

**Endpointing uses audio time.** `UtteranceRecorder` counts frames rather than reading the wall clock, so its behaviour is deterministic and unit-testable. It keeps about 320 ms of *pre-roll* so your first syllable isn't clipped, and it ignores bursts shorter than 240 ms (coughs, clicks).

**Sentence streaming.** `SentenceChunker` emits sentences from the token stream as soon as they end. A producer/consumer queue lets TTS work on sentence *n* while the LLM writes sentence *n+1*. Time to first audio is roughly STT + LLM-first-sentence + TTS-one-sentence. That's typically 1–2 s on a CPU with `llama3.2:3b`. See [ADR-0006](../adr/0006-sentence-streaming-and-playback-acks.md).

**Text is made speakable.** `to_speakable` strips Markdown, code and URLs before TTS, and the persona prompt asks for plain spoken prose.

**Playback acknowledgements.** The server only knows Jarvis has finished speaking when the client says so (`playback_ended`). This keeps the microphone closed while Jarvis talks, so it doesn't hear itself, and it times follow-up listening correctly.

## The visualizer

The orb (`components/hud/orbRenderer.ts`) is drawn on a 2D canvas at display refresh rate.

- **Input**: `AnalyserNode.getByteFrequencyData` on Jarvis's output while speaking, or on your mic while listening (`VoiceAssistant.levelSource()`).
- **Level**: mean energy of the voice band, passed through `perceptualLevel` (1 − e^(−gx)) with a fast attack and a slow release. That asymmetry is what makes it visibly "bounce" on each word.
- **Layers**: ambient glow, compass ticks and rotating arcs, 128 mirrored spectrum bars, a liquid membrane whose ripple amplitude follows the level, and the luminous core.
- **States**: colour cross-fades over about 250 ms. Idle cyan breathes slowly, listening turns mint, thinking turns gold with a chasing comet, and speaking is bright cyan.

Captions use the per-word timestamps from Kokoro. `SpeechPlayer` records when each segment actually starts on the `AudioContext` clock, and `activeWordIndex` binary-searches the current word every frame.

## Latency budget (CPU-only laptop, indicative)

| Stage                         | Typical      |
| ----------------------------- | ------------ |
| Wake → greeting audio         | < 300 ms     |
| End-of-speech detection       | 800 ms (configurable) |
| Whisper `base.en`, 3 s clip   | 300–700 ms   |
| LLM first sentence (3B)       | 400–1200 ms  |
| Kokoro, one sentence          | 200–600 ms   |
