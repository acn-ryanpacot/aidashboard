"""Adapters that can be tested without optional heavy dependencies."""

from __future__ import annotations

import io
import json
import wave

import httpx
import numpy as np
import pytest

from jarvis_core.adapters.audio import encode_wav, float_to_pcm16, pcm16_to_float32
from jarvis_core.adapters.llm.ollama import OllamaLanguageModel
from jarvis_core.adapters.vad.energy import EnergyVoiceActivityDetector
from jarvis_core.domain.errors import LanguageModelError
from jarvis_core.domain.models import AudioClip, ChatMessage, Role

# --------------------------------------------------------------------- audio


def test_pcm_float_round_trip() -> None:
    original = np.array([0.0, 0.5, -0.5, 0.999], dtype=np.float32)
    restored = pcm16_to_float32(float_to_pcm16(original))
    assert np.allclose(original, restored, atol=1e-3)


def test_float_to_pcm16_clips_out_of_range() -> None:
    pcm = np.frombuffer(float_to_pcm16([2.0, -2.0]), dtype="<i2")
    assert pcm.tolist() == [32767, -32767]


def test_encode_wav_header() -> None:
    clip = AudioClip(b"\x00\x00" * 2400, 24_000)
    with wave.open(io.BytesIO(encode_wav(clip))) as wav:
        assert wav.getframerate() == 24_000
        assert wav.getnchannels() == 1
        assert wav.getnframes() == 2400
    assert clip.duration_seconds == pytest.approx(0.1)


# ----------------------------------------------------------------------- VAD


def test_energy_vad_separates_speech_from_silence() -> None:
    vad = EnergyVoiceActivityDetector()
    silence = float_to_pcm16(np.zeros(1280))
    tone = float_to_pcm16(0.3 * np.sin(np.linspace(0, 200 * np.pi, 1280)))
    assert not vad.is_speech(silence)
    assert vad.is_speech(tone)
    assert not vad.is_speech(b"")


# -------------------------------------------------------------------- Ollama


def _ollama(handler: httpx.MockTransport) -> OllamaLanguageModel:
    client = httpx.AsyncClient(base_url="http://ollama", transport=handler)
    return OllamaLanguageModel(base_url="http://ollama", model="test:1b", client=client)


MESSAGES = [ChatMessage(Role.USER, "hi")]


async def test_ollama_streams_deltas() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        lines = [
            {"message": {"content": "Hello"}, "done": False},
            {"message": {"content": " Ryan."}, "done": False},
            {"message": {"content": ""}, "done": True},
        ]
        return httpx.Response(200, text="\n".join(json.dumps(line) for line in lines))

    llm = _ollama(httpx.MockTransport(handler))
    assert [d async for d in llm.stream_chat(MESSAGES)] == ["Hello", " Ryan."]
    assert captured["model"] == "test:1b"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    await llm.aclose()


async def test_ollama_missing_model_is_explained() -> None:
    llm = _ollama(httpx.MockTransport(lambda _: httpx.Response(404, text="not found")))
    with pytest.raises(LanguageModelError, match="ollama pull test:1b"):
        _ = [d async for d in llm.stream_chat(MESSAGES)]


async def test_ollama_unreachable_raises_domain_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    llm = _ollama(httpx.MockTransport(handler))
    with pytest.raises(LanguageModelError, match="Is Ollama running"):
        _ = [d async for d in llm.stream_chat(MESSAGES)]


async def test_ollama_inline_error_raises() -> None:
    llm = _ollama(httpx.MockTransport(lambda _: httpx.Response(200, text='{"error": "boom"}')))
    with pytest.raises(LanguageModelError, match="boom"):
        _ = [d async for d in llm.stream_chat(MESSAGES)]
