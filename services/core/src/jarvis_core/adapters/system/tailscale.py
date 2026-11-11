"""Read Tailscale's status from its CLI (read-only).

Jarvis never changes Tailscale's configuration. It only asks:

* ``tailscale status --json`` for whether this PC is on the tailnet, and its name;
* ``tailscale serve status --json`` for whether ``tailscale serve`` forwards an
  HTTPS address to the Jarvis port, which is what the phone opens.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from pathlib import Path
from typing import Any

import structlog

from jarvis_core.domain.records import RemoteAccessStatus

log = structlog.get_logger(__name__)

#: Where the Windows installer puts the CLI if it isn't on PATH.
_WINDOWS_CLI = Path(r"C:\Program Files\Tailscale\tailscale.exe")


def find_cli() -> str | None:
    """Path of the ``tailscale`` CLI, if installed."""
    found = shutil.which("tailscale")
    if found:
        return found
    return str(_WINDOWS_CLI) if _WINDOWS_CLI.is_file() else None


def parse_status(data: Any) -> tuple[bool, str]:
    """``(running, dns_name)`` from ``tailscale status --json``."""
    if not isinstance(data, dict):
        return False, ""
    me = data.get("Self")
    dns_name = str(me.get("DNSName") or "").rstrip(".") if isinstance(me, dict) else ""
    return data.get("BackendState") == "Running", dns_name


def parse_serve(data: Any, port: int) -> str:
    """The HTTPS URL that ``tailscale serve`` forwards to ``port`` ("" if none).

    The JSON maps ``"host:443"`` to handlers like ``{"/": {"Proxy":
    "http://127.0.0.1:8765"}}``.
    """
    web = data.get("Web") if isinstance(data, dict) else None
    if not isinstance(web, dict):
        return ""
    for host_port, config in web.items():
        handlers = config.get("Handlers") if isinstance(config, dict) else None
        if not isinstance(handlers, dict):
            continue
        root = handlers.get("/")
        proxy = str(root.get("Proxy", "")) if isinstance(root, dict) else ""
        target = proxy.rstrip("/").rsplit(":", 1)[-1]
        if target != str(port):
            continue
        host, _, public_port = str(host_port).rpartition(":")
        host = host or str(host_port)
        suffix = "" if public_port in ("", "443") else f":{public_port}"
        return f"https://{host}{suffix}"
    return ""


class TailscaleProbe:
    """Implements :class:`~jarvis_core.domain.ports.RemoteAccessProbe`.

    Args:
        port: The port Jarvis listens on (what ``serve`` should forward to).
        cli: Path of the Tailscale CLI (``None`` = look it up).
        timeout_s: Per-command time limit.
    """

    def __init__(self, port: int, *, cli: str | None = None, timeout_s: float = 3.0) -> None:
        self._port = port
        self._cli = cli
        self._timeout_s = timeout_s
        self._cached: tuple[float, RemoteAccessStatus] | None = None

    async def status(self) -> RemoteAccessStatus:
        """Current status, cached for ten seconds (never raises)."""
        now = time.monotonic()
        if self._cached is None or now - self._cached[0] > 10.0:
            self._cached = (now, await self._read())
        return self._cached[1]

    async def _read(self) -> RemoteAccessStatus:
        cli = self._cli or find_cli()
        if cli is None:
            return RemoteAccessStatus(installed=False)
        running, dns_name = parse_status(await self._json(cli, "status", "--json"))
        public_url = (
            parse_serve(await self._json(cli, "serve", "status", "--json"), self._port)
            if running
            else ""
        )
        return RemoteAccessStatus(True, running, dns_name, public_url)

    async def _json(self, cli: str, *args: str) -> Any:
        try:
            process = await asyncio.create_subprocess_exec(
                cli,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as exc:
            log.info("tailscale_cli_failed", args=args, error=str(exc))
            return None
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), self._timeout_s)
        except TimeoutError:
            process.kill()
            await process.wait()
            log.info("tailscale_cli_timeout", args=args)
            return None
        try:
            return json.loads(stdout or b"null")
        except ValueError:
            return None
