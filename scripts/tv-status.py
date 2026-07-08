#!/usr/bin/env python3
"""Show what the TV is doing: inputs, foreground app, current picture mode.

Usage (host/key default to LGTV_HOST / LGTV_KEY, same env as the daemon):

    venv/bin/python scripts/tv-status.py
    venv/bin/python scripts/tv-status.py --host 10.15.4.183 --key <key>

Reading the current picture mode uses getSystemSettings, whose readable-key
whitelist varies by firmware (the C9 refuses eyeComfortMode, for example) —
when refused, the script says so instead of failing.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

CONNECT_TIMEOUT = 15.0
REQUEST_TIMEOUT = 10.0


async def status(host: str, key: str | None) -> None:
    from bscpylgtv import WebOsClient
    client = await asyncio.wait_for(
        WebOsClient.create(host, client_key=key, states=[], ping_interval=None),
        CONNECT_TIMEOUT)
    await asyncio.wait_for(client.connect(), CONNECT_TIMEOUT)
    try:
        res = await asyncio.wait_for(client.get_inputs(), REQUEST_TIMEOUT)
        devices = res.get("devices", []) if isinstance(res, dict) else (res or [])
        print("Inputs (* = device connected):")
        for d in devices:
            mark = "*" if d.get("connected") else " "
            print(f"  {mark} {d.get('id', '?'):<12} label={d.get('label')!r} "
                  f"icon={d.get('icon')}")

        app = await asyncio.wait_for(client.get_current_app(), REQUEST_TIMEOUT)
        print(f"\nForeground app: {app or '(home)'}")

        try:
            res = await asyncio.wait_for(
                client.get_system_settings("picture", ["pictureMode"]),
                REQUEST_TIMEOUT)
            mode = (res or {}).get("settings", {}).get("pictureMode")
            print(f"Current picture mode: {mode}")
        except asyncio.TimeoutError:
            raise
        except Exception as exc:
            print(f"Current picture mode: not readable on this firmware ({exc})")
    finally:
        try:
            await asyncio.wait_for(client.disconnect(), 5.0)
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default=os.environ.get("LGTV_HOST"),
                    help="TV IP (default: $LGTV_HOST)")
    ap.add_argument("--key", default=os.environ.get("LGTV_KEY"),
                    help="webOS pairing key (default: $LGTV_KEY)")
    args = ap.parse_args()
    if not args.host:
        ap.error("--host or LGTV_HOST required")
    asyncio.run(status(args.host, args.key))
    return 0


if __name__ == "__main__":
    sys.exit(main())
