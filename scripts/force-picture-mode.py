#!/usr/bin/env python3
"""Force picture modes into every input x dynamic-range slot on the TV.

LG keys the picture mode per input AND per dynamic range (category
"picture$<input>.x.2d.<dynamicRange>"), so changing it in the menu only
affects the slot you happen to be watching. This script writes your chosen
mode into every slot in one pass.

Usage (host/key default to LGTV_HOST / LGTV_KEY, same env as the daemon):

    ./force-picture-mode.py --dry-run                 # show the plan
    ./force-picture-mode.py                           # apply defaults below
    ./force-picture-mode.py sdr=cinema hdr=hdrVivid   # override per range
    ./force-picture-mode.py --inputs hdmi1,hdmi2 sdr=game

The mode name must match the dynamic range family (SDR slots take cinema/
expert1/game/..., HDR slots hdr*, Dolby Vision slots dolbyHdr*) — see
bscpylgtv docs/available_settings_C9.md for the full enums.

Caveat: the scoped-category luna syntax is documented against newer models
(OLED C3). Expected to work on the C9 (its settings doc ships these exact
input/dynamic-range enums), but verify one slot first:

    ./force-picture-mode.py --inputs hdmi1 sdr=expert1

Each write is read back where the firmware allows; the summary says which
slots were confirmed, written blind, or rejected.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

# hdmiN_pc are separate slots that take over when an input's icon is set to
# PC — include them so a relabeled input doesn't dodge the sweep.
DEFAULT_INPUTS = [
    "default", "ip", "dtv",
    "hdmi1", "hdmi2", "hdmi3", "hdmi4",
    "hdmi1_pc", "hdmi2_pc", "hdmi3_pc", "hdmi4_pc",
]

# One mode per dynamic range; ALLM variants are the slots a console
# negotiates, hence the game modes.
DEFAULT_MODES = {
    "sdr": "expert1",
    "sdrALLM": "game",
    "hdr": "hdrCinema",
    "hdrALLM": "hdrGame",
    "dolbyHdr": "dolbyHdrCinema",
    "dolbyHdrALLM": "dolbyHdrGame",
    "technicolorHdr": "technicolorHdrCinema",
    "technicolorHdrALLM": "technicolorHdrGame",
}

CONNECT_TIMEOUT = 15.0
REQUEST_TIMEOUT = 10.0


def parse_overrides(pairs: list[str]) -> dict[str, str]:
    modes = dict(DEFAULT_MODES)
    for pair in pairs:
        dr, sep, mode = pair.partition("=")
        if not sep or not mode or dr not in DEFAULT_MODES:
            raise SystemExit(
                f"bad override {pair!r}: expected <dynamicRange>=<mode> with "
                f"dynamicRange one of {', '.join(DEFAULT_MODES)}")
        modes[dr] = mode
    return modes


async def read_back(client, tv_input: str, dynamic_range: str):
    """Best-effort read of a slot's pictureMode; None when unsupported."""
    try:
        res = await asyncio.wait_for(
            client.get_system_settings(
                f"picture${tv_input}.x.2d.{dynamic_range}", ["pictureMode"]),
            REQUEST_TIMEOUT)
        return (res or {}).get("settings", {}).get("pictureMode")
    except Exception:
        return None


async def apply(host: str, key: str | None, inputs: list[str],
                modes: dict[str, str]) -> int:
    from bscpylgtv import WebOsClient
    client = await asyncio.wait_for(
        WebOsClient.create(host, client_key=key, states=[], ping_interval=None),
        CONNECT_TIMEOUT)
    await asyncio.wait_for(client.connect(), CONNECT_TIMEOUT)
    confirmed = blind = rejected = 0
    try:
        for tv_input in inputs:
            for dynamic_range, mode in modes.items():
                slot = f"{tv_input}/{dynamic_range}"
                try:
                    await asyncio.wait_for(
                        client.set_picture_mode(mode, tv_input, dynamic_range),
                        REQUEST_TIMEOUT)
                except Exception as exc:
                    rejected += 1
                    print(f"  REJECTED  {slot} <- {mode}  ({exc})")
                    continue
                seen = await read_back(client, tv_input, dynamic_range)
                if seen == mode:
                    confirmed += 1
                    print(f"  ok        {slot} <- {mode}")
                elif seen is None:
                    blind += 1
                    print(f"  written   {slot} <- {mode}  (no read-back)")
                else:
                    rejected += 1
                    print(f"  MISMATCH  {slot} <- {mode}  (reads {seen!r})")
    finally:
        try:
            await asyncio.wait_for(client.disconnect(), 5.0)
        except Exception:
            pass
    print(f"\n{confirmed} confirmed, {blind} written without read-back, "
          f"{rejected} rejected/mismatched")
    return 1 if rejected else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("overrides", nargs="*", metavar="dynamicRange=mode",
                    help=f"override the default mode map: {DEFAULT_MODES}")
    ap.add_argument("--inputs", default=",".join(DEFAULT_INPUTS),
                    help="comma-separated input list (default: all)")
    ap.add_argument("--host", default=os.environ.get("LGTV_HOST"),
                    help="TV IP (default: $LGTV_HOST)")
    ap.add_argument("--key", default=os.environ.get("LGTV_KEY"),
                    help="webOS pairing key (default: $LGTV_KEY)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan without touching the TV")
    args = ap.parse_args()

    modes = parse_overrides(args.overrides)
    inputs = [i.strip() for i in args.inputs.split(",") if i.strip()]
    if args.dry_run:
        for tv_input in inputs:
            for dynamic_range, mode in modes.items():
                print(f"  would set {tv_input}/{dynamic_range} <- {mode}")
        return 0
    if not args.host:
        ap.error("--host or LGTV_HOST required")
    return asyncio.run(apply(args.host, args.key, inputs, modes))


if __name__ == "__main__":
    sys.exit(main())
