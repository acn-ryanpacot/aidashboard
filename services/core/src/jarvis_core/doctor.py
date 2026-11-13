"""``jarvis-doctor``: check that every part of Jarvis is installed and working.

Run it on a new machine after following ``docs/guides/personal-pc-setup.md``::

    uv run jarvis-doctor

Each check prints ✓ (ok), ! (optional / degraded) or ✗ (broken) with a hint.
The exit code is non-zero if any required check fails.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import socket
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import httpx

from jarvis_core import __version__
from jarvis_core.config import Settings


class Status(StrEnum):
    """Outcome of a check."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class Check:
    """One diagnostic result."""

    name: str
    status: Status
    detail: str
    hint: str = ""


SYMBOL = {Status.OK: "✓", Status.WARN: "!", Status.FAIL: "✗"}


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


# ------------------------------------------------------------------- checks


def check_python() -> Check:
    """Python 3.11 to 3.13 is supported; 3.12 is what the project pins."""
    version = sys.version_info
    label = f"{version.major}.{version.minor}.{version.micro}"
    if (3, 11) <= version[:2] <= (3, 13):
        return Check("Python", Status.OK, label)
    return Check(
        "Python",
        Status.WARN,
        label,
        "Speech libraries publish wheels for 3.11-3.13. Use `uv sync` (it installs 3.12).",
    )


def check_package(module: str, label: str, extra: str, *, required: bool = False) -> Check:
    """Whether an optional dependency is importable."""
    if _has(module):
        return Check(label, Status.OK, "installed")
    return Check(
        label,
        Status.FAIL if required else Status.WARN,
        "not installed",
        f"uv sync --group dev --extra {extra} (plus --extra cu128 on an NVIDIA GPU)",
    )


def check_torch() -> Check:
    """PyTorch build and whether it sees the GPU."""
    if not _has("torch"):
        return Check("PyTorch", Status.WARN, "not installed", "Comes with --extra voice.")
    import torch

    if torch.cuda.is_available():
        return Check(
            "PyTorch", Status.OK, f"{torch.__version__} · CUDA · {torch.cuda.get_device_name(0)}"
        )
    hint = (
        "CPU-only build. For the GPU: uv sync --group dev --extra voice --extra cu128"
        if "+cpu" in torch.__version__ or torch.version.cuda is None
        else "CUDA build but no GPU visible: update the NVIDIA driver, then reboot."
    )
    return Check("PyTorch", Status.WARN, f"{torch.__version__} · CPU", hint)


def check_whisper_gpu(settings: Settings) -> Check:
    """Whether faster-whisper (CTranslate2) can use CUDA."""
    if not _has("ctranslate2"):
        return Check("Whisper GPU", Status.WARN, "faster-whisper not installed")
    if _has("torch"):
        importlib.import_module("torch")  # registers bundled CUDA DLLs on Windows
    import ctranslate2

    count = ctranslate2.get_cuda_device_count()
    if count > 0:
        return Check("Whisper GPU", Status.OK, f"{count} CUDA device(s)")
    status = Status.FAIL if settings.stt_device == "cuda" else Status.WARN
    return Check(
        "Whisper GPU",
        status,
        "CPU only",
        "Fine for base.en/small.en. For the GPU see the setup guide's 'Whisper on the GPU'.",
    )


def check_nvidia() -> Check:
    """Whether the NVIDIA driver is installed."""
    if shutil.which("nvidia-smi") is None:
        return Check(
            "NVIDIA driver",
            Status.WARN,
            "nvidia-smi not found",
            "Install the latest Game/Studio driver.",
        )
    from jarvis_core.adapters.system.monitor import query_nvidia_smi

    gpus = query_nvidia_smi()
    if not gpus:
        return Check("NVIDIA driver", Status.WARN, "no GPU reported")
    return Check(
        "NVIDIA driver",
        Status.OK,
        ", ".join(f"{g.name} ({g.memory_total_mb / 1024:.0f} GB)" for g in gpus),
    )


def check_ollama(settings: Settings) -> list[Check]:
    """Ollama is running and has the configured models."""
    try:
        tags = httpx.get(f"{settings.llm_base_url}/api/tags", timeout=3).json()
    except (httpx.HTTPError, ValueError):
        return [
            Check(
                "Ollama",
                Status.FAIL,
                f"unreachable at {settings.llm_base_url}",
                "Install from https://ollama.com and make sure it is running (tray icon).",
            )
        ]
    installed = {m.get("name", "") for m in tags.get("models", [])}

    def has(model: str) -> bool:
        return bool(installed & {model, f"{model}:latest"})

    checks = [Check("Ollama", Status.OK, f"{len(installed)} model(s) installed")]
    checks.append(
        Check("LLM model", Status.OK, settings.llm_model)
        if has(settings.llm_model)
        else Check(
            "LLM model",
            Status.FAIL,
            f"{settings.llm_model} missing",
            f"ollama pull {settings.llm_model}",
        )
    )
    checks.append(
        Check("Embedding model", Status.OK, settings.embedding_model)
        if has(settings.embedding_model)
        else Check(
            "Embedding model",
            Status.WARN,
            f"{settings.embedding_model} missing (memory falls back to keywords)",
            f"ollama pull {settings.embedding_model}",
        )
    )
    return checks


def check_espeak() -> Check:
    """espeak-ng improves Kokoro's pronunciation of unusual words."""
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        return Check("espeak-ng", Status.OK, "found")
    return Check(
        "espeak-ng",
        Status.WARN,
        "not found (optional)",
        "Install the MSI from https://github.com/espeak-ng/espeak-ng/releases",
    )


def check_data_dir(settings: Settings) -> Check:
    """The data directory is writable."""
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.data_dir / ".doctor"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return Check(
            "Data directory", Status.FAIL, str(exc), "Set JARVIS_DATA_DIR to a writable folder."
        )
    return Check("Data directory", Status.OK, str(settings.data_dir))


def check_port(settings: Settings) -> Check:
    """Whether the service port is free (or already serving Jarvis)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        in_use = sock.connect_ex((settings.host, settings.port)) == 0
    if not in_use:
        return Check("Port", Status.OK, f"{settings.host}:{settings.port} free")
    base = f"http://{settings.host}:{settings.port}"
    try:
        health = httpx.get(f"{base}/api/health", timeout=2).json()
        return Check("Port", Status.OK, f"Jarvis {health.get('version')} already running")
    except (httpx.HTTPError, ValueError):
        if _is_pisotiyempo_feed(base):
            return Check(
                "Port",
                Status.FAIL,
                f"{settings.port} used by PisoTiyempo's dashboard feed",
                r"Add feedPort=8766 to %APPDATA%\PisoTiyempo\config.properties, then restart it.",
            )
        return Check(
            "Port",
            Status.FAIL,
            f"{settings.port} used by another program",
            "Free the port or set JARVIS_PORT (and VITE_JARVIS_CORE_URL in the UI).",
        )


def _is_pisotiyempo_feed(base_url: str) -> bool:
    """Whether ``base_url`` serves PisoTiyempo's feed (its index lists ``/api/summary``)."""
    try:
        index = httpx.get(f"{base_url}/api", timeout=2).json()
    except (httpx.HTTPError, ValueError):
        return False
    return isinstance(index, dict) and "/api/summary" in index.get("endpoints", [])


def check_pisotiyempo(settings: Settings) -> Check:
    """Whether the PisoTiyempo portfolio can be read (live feed or export files)."""
    from jarvis_core.adapters.portfolio.pisotiyempo import default_export_dir

    url = settings.portfolio_feed_url.rstrip("/")
    if url and _is_pisotiyempo_feed(url):
        return Check("PisoTiyempo", Status.OK, f"live feed at {url}")
    folder = (
        Path(settings.portfolio_export_dir).expanduser()
        if settings.portfolio_export_dir
        else default_export_dir()
    )
    if (folder / "summary.json").is_file():
        return Check("PisoTiyempo", Status.OK, f"export files in {folder} (app closed)")
    return Check(
        "PisoTiyempo",
        Status.WARN,
        "not found (the Portfolio widget will say so)",
        "Optional. See docs/guides/pisotiyempo.md, or set JARVIS_PORTFOLIO_ENABLED=false.",
    )


def check_pisotiyempo_alerts(settings: Settings) -> Check:
    """Whether PisoTiyempo's database (with your alert rules) can be read."""
    from jarvis_core.adapters.portfolio.pisotiyempo import default_database_path

    path = (
        Path(settings.portfolio_database).expanduser()
        if settings.portfolio_database
        else default_database_path()
    )
    if path.is_file():
        return Check("PisoTiyempo alerts", Status.OK, f"reading {path}")
    return Check(
        "PisoTiyempo alerts",
        Status.WARN,
        f"no database at {path}",
        "Install the PisoTiyempo desktop app, or set JARVIS_PORTFOLIO_ALERTS_ENABLED=false.",
    )


def check_web_ui(settings: Settings) -> Check:
    """Whether the dashboard is built, so phones can load it from the core."""
    from jarvis_core.api.app import web_ui_folder

    folder = web_ui_folder(settings)
    if folder is not None:
        return Check("Web UI (phones)", Status.OK, f"serving {folder}")
    return Check(
        "Web UI (phones)",
        Status.WARN,
        "not built (only needed for phone access)",
        "From the repository root: pnpm --filter @jarvis/desktop build",
    )


def check_tailscale(settings: Settings) -> Check:
    """Whether Tailscale publishes Jarvis to your phone (optional)."""
    import asyncio

    from jarvis_core.adapters.system.tailscale import TailscaleProbe

    status = asyncio.run(TailscaleProbe(settings.port).status())
    if not status.installed:
        return Check(
            "Tailscale (phones)",
            Status.WARN,
            "not installed (only needed for phone access)",
            "See docs/guides/phone-access.md",
        )
    if not status.running:
        return Check(
            "Tailscale (phones)", Status.WARN, "installed but not connected", "tailscale up"
        )
    if not status.public_url:
        return Check(
            "Tailscale (phones)",
            Status.WARN,
            f"connected as {status.dns_name}, but Jarvis isn't published",
            f"tailscale serve --bg {settings.port}",
        )
    return Check("Tailscale (phones)", Status.OK, f"phones open {status.public_url}")


def check_web_search(settings: Settings) -> Check:
    """Which web search Jarvis will use."""
    if not settings.tools_enabled or settings.web_search == "off":
        return Check("Web search", Status.WARN, "off", "Set JARVIS_WEB_SEARCH=auto to enable it.")
    url = settings.searxng_url.rstrip("/")
    fallback = settings.web_search == "auto"
    if url and settings.web_search != "duckduckgo":
        try:
            response = httpx.get(
                f"{url}/search", params={"q": "jarvis", "format": "json"}, timeout=5
            )
            response.raise_for_status()
            response.json()
        except (httpx.HTTPError, ValueError):
            return Check(
                "Web search",
                Status.WARN,
                f"SearXNG not answering at {url}"
                + (" (using DuckDuckGo meanwhile)" if fallback else ""),
                "cd services/searxng; docker compose up -d   (JSON must be enabled; see "
                "docs/guides/web-search.md)",
            )
        return Check("Web search", Status.OK, f"SearXNG at {url}")
    return Check(
        "Web search",
        Status.OK,
        "DuckDuckGo (no setup needed)",
        "For a more reliable, private search run SearXNG: docs/guides/web-search.md",
    )


def documents_folder(settings: Settings) -> str:
    """The documents folder: the Settings screen's choice, else ``JARVIS_DOCUMENTS_DIR``."""
    import json
    import sqlite3

    from jarvis_core.application.runtime_settings import PREFERENCE_KEY

    database = settings.data_dir / "jarvis.db"
    if database.is_file():
        try:
            with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as conn:
                row = conn.execute(
                    "SELECT value FROM preferences WHERE key = ?", (PREFERENCE_KEY,)
                ).fetchone()
            stored = json.loads(row[0]) if row else {}
            if isinstance(stored, dict) and "documents_dir" in stored:
                return str(stored["documents_dir"])
        except (sqlite3.Error, ValueError):
            pass
    return settings.documents_dir


def check_documents(settings: Settings) -> Check:
    """Whether a documents folder is set and how many files Jarvis can read in it."""
    from jarvis_core.adapters.documents.extractors import kind_of

    folder_text = documents_folder(settings).strip().strip('"')
    if not folder_text:
        return Check(
            "Documents folder",
            Status.WARN,
            "not set (Jarvis can't read your files yet)",
            "Optional. Dashboard → Settings → Knowledge → Documents folder",
        )
    folder = Path(folder_text).expanduser()
    if not folder.is_dir():
        return Check(
            "Documents folder", Status.WARN, f"{folder} doesn't exist", "Fix it in Settings"
        )
    kinds: dict[str, int] = {}
    for path in folder.rglob("*"):
        kind = kind_of(path)
        if kind and path.is_file() and not path.name.startswith(("~$", ".")):
            kinds[kind] = kinds.get(kind, 0) + 1
    summary = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())) or "no readable files"
    return Check("Documents folder", Status.OK, f"{folder}: {summary}")


def run_checks(settings: Settings) -> list[Check]:
    """Run every check (never raises)."""
    checks: list[Check] = [check_python(), check_data_dir(settings), check_port(settings)]
    checks += [check_web_ui(settings), check_tailscale(settings)]
    if settings.portfolio_enabled:
        checks.append(check_pisotiyempo(settings))
        if settings.portfolio_alerts_enabled:
            checks.append(check_pisotiyempo_alerts(settings))
    checks += check_ollama(settings)
    if settings.tools_enabled:
        checks += [check_web_search(settings), check_documents(settings)]
    voice: list[tuple[str, str, str, bool]] = [
        ("faster_whisper", "faster-whisper (STT)", "voice", settings.stt_engine != "none"),
        ("kokoro", "Kokoro (TTS)", "voice", settings.tts_engine != "none"),
        ("openwakeword", "openWakeWord", "voice", settings.wake_engine != "none"),
        ("webrtcvad", "WebRTC VAD", "voice", settings.vad_engine == "webrtc"),
        ("silero_vad", "Silero VAD", "voice", settings.vad_engine == "silero"),
        ("speechbrain", "SpeechBrain (voice ID)", "speaker", settings.speaker_verification),
        ("mcp", "MCP client", "mcp", bool(settings.mcp_servers)),
    ]
    for module, label, extra, required in voice:
        checks.append(check_package(module, label, extra, required=required))
    guarded: list[Callable[[], Check]] = [
        check_nvidia,
        check_torch,
        lambda: check_whisper_gpu(settings),
        check_espeak,
    ]
    for check in guarded:
        try:
            checks.append(check())
        except Exception as exc:  # a diagnostic must never crash the doctor
            checks.append(Check(getattr(check, "__name__", "check"), Status.WARN, f"error: {exc}"))
    return checks


def main() -> None:
    """Entry point for ``jarvis-doctor``."""
    if os.name == "nt":
        with __import__("contextlib").suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    settings = Settings()
    print(f"Jarvis OS doctor · core {__version__}\n")
    checks = run_checks(settings)
    width = max(len(c.name) for c in checks)
    for check in checks:
        print(f"  {SYMBOL[check.status]} {check.name.ljust(width)}  {check.detail}")
        if check.hint and check.status is not Status.OK:
            print(f"    {' ' * width}  → {check.hint}")
    failures = [c for c in checks if c.status is Status.FAIL]
    warnings = [c for c in checks if c.status is Status.WARN]
    print(
        f"\n{len(checks) - len(failures) - len(warnings)} ok · {len(warnings)} warning(s) · "
        f"{len(failures)} problem(s)"
    )
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
