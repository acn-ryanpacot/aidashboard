"""``jarvis-token``: pair, list and revoke remote devices from a terminal.

The dashboard's Settings → Phone access does the same with a QR code; this
is for headless setups or when the UI isn't at hand::

    uv run jarvis-token create "Ryan's phone"
    uv run jarvis-token list
    uv run jarvis-token revoke 3
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from jarvis_core.adapters.persistence.database import Database
from jarvis_core.adapters.persistence.repositories import SqliteDeviceTokenRepository
from jarvis_core.adapters.system.tailscale import TailscaleProbe
from jarvis_core.application.devices import DeviceAccess
from jarvis_core.config import Settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis-token", description="Manage devices allowed to reach Jarvis remotely."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="pair a device and print its token once")
    create.add_argument("name", nargs="?", default="Phone")
    commands.add_parser("list", help="list paired devices")
    revoke = commands.add_parser("revoke", help="unpair a device")
    revoke.add_argument("id", type=int)
    return parser


async def _run(args: argparse.Namespace, settings: Settings) -> int:
    database = Database(settings.data_dir / "jarvis.db")
    try:
        access = DeviceAccess(SqliteDeviceTokenRepository(database))
        if args.command == "create":
            device, token = await access.create(args.name)
            remote = await TailscaleProbe(settings.port).status()
            print(f"Paired #{device.id} {device.name}. Token (shown only once):\n\n  {token}\n")
            if remote.public_url:
                print(
                    f"Open this on the phone to pair it:\n\n  {remote.public_url}/#pair={token}\n"
                )
            else:
                print("Run `tailscale serve --bg 8765`, then open its https address on the phone")
                print("and paste the token. See docs/guides/phone-access.md.")
            return 0
        if args.command == "list":
            devices = await access.list_all()
            if not devices:
                print("No paired devices.")
            for d in devices:
                used = (
                    f"last used {d.last_used_at:%Y-%m-%d %H:%M} UTC"
                    if d.last_used_at
                    else "never used"
                )
                print(f"#{d.id:<3} {d.name:<24} paired {d.created_at:%Y-%m-%d}  {used}")
            return 0
        if await access.revoke(args.id):
            print(f"Revoked device #{args.id}.")
            return 0
        print(f"No device #{args.id}.", file=sys.stderr)
        return 1
    finally:
        database.close()


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    """Entry point for ``jarvis-token``."""
    args = _parser().parse_args(argv)
    return asyncio.run(_run(args, settings or Settings()))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
