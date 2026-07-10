"""Daemon that keeps the C9's ISF Bright/Dark preset sticky across app switches.

Holds a persistent webOS connection with two subscriptions — current app and
picture settings — and feeds their events to a pure `preset.Keeper`. When an app
switch flips the ISF variant, it blind-writes `pictureMode` back (the key is
write-only on this firmware, same as eyeComfortMode). Every await is
timeout-guarded: this TV can drop off the network without closing TCP, and an
unguarded await then hangs near-forever (tv-dsp's dead-connection lesson).

Config is env-only (12-factor); see systemd/lg-tv-enhancer.env.example.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from preset import parse_fingerprint


@dataclass(frozen=True)
class Config:
    host: str
    key: str | None
    bright_fp: tuple[int, int, int]
    dark_fp: tuple[int, int, int]
    bright_mode: str
    dark_mode: str
    settle_secs: float


def load_config(env: Mapping[str, str] = os.environ) -> Config:
    if not env.get("LGTV_HOST"):
        raise SystemExit("missing required environment: LGTV_HOST")
    return Config(
        host=env["LGTV_HOST"],
        key=env.get("LGTV_KEY") or None,
        bright_fp=parse_fingerprint(env.get("LGTV_PRESET_BRIGHT", "90,90,65")),
        dark_fp=parse_fingerprint(env.get("LGTV_PRESET_DARK", "85,10,50")),
        bright_mode=env.get("LGTV_MODE_BRIGHT", "expert1"),
        dark_mode=env.get("LGTV_MODE_DARK", "expert2"),
        settle_secs=float(env.get("LGTV_SETTLE_SECS", "3")),
    )
