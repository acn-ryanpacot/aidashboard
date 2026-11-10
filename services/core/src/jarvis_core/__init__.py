"""Jarvis OS core service.

The package is organised as a hexagonal ("ports and adapters") architecture:

* :mod:`jarvis_core.domain` — pure business types and the *ports* (interfaces)
  the rest of the system depends on. No I/O, no third-party SDKs.
* :mod:`jarvis_core.application` — use cases that orchestrate ports, e.g. the
  :class:`~jarvis_core.application.voice_session.VoiceSession` state machine.
* :mod:`jarvis_core.adapters` — concrete implementations of the ports
  (Ollama, faster-whisper, Kokoro, openWakeWord, WebRTC VAD …).
* :mod:`jarvis_core.api` — the FastAPI delivery layer (HTTP + WebSocket).
* :mod:`jarvis_core.container` — the composition root that wires it all up.
"""

__version__ = "0.1.0"
