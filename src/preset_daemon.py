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

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping

from preset import Correction, Keeper, parse_fingerprint


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


log = logging.getLogger("lg-tv-preset")

REQUEST_TIMEOUT = 10.0

Callback = Callable[..., Awaitable[None]]


def build_keeper(cfg: Config) -> Keeper:
    return Keeper(bright_fp=cfg.bright_fp, dark_fp=cfg.dark_fp,
                  bright_mode=cfg.bright_mode, dark_mode=cfg.dark_mode,
                  settle_secs=cfg.settle_secs)


async def _guarded_write(client, mode: str) -> None:
    """Blind-write pictureMode, logging the outcome. Never raises (it runs in a
    detached task, so an unhandled error would just vanish into the loop)."""
    try:
        await asyncio.wait_for(
            client.set_settings("picture", {"pictureMode": mode}), REQUEST_TIMEOUT)
        log.info("restored pictureMode=%s", mode)
    except Exception as exc:  # noqa: BLE001 - detached task, log and move on
        log.warning("preset write failed (%s: %s)", type(exc).__name__, exc)


def wire(keeper: Keeper, client, *, clock: Callable[[], float],
         spawn: Callable[[Awaitable[None]], object] = asyncio.create_task) -> tuple[Callback, Callback]:
    """Build the (on_pic, on_app) subscription callbacks around a Keeper.

    The write is scheduled via `spawn` rather than awaited: awaiting a request
    inside a subscription callback deadlocks the client's consumer loop.
    """
    async def on_pic(settings: Mapping[str, object]) -> None:
        correction: Correction | None = keeper.on_picture_change(settings, clock())
        if correction is not None:
            log.info("app switch flipped away from %s; restoring", correction.to_preset)
            spawn(_guarded_write(client, correction.mode))

    async def on_app(app: object) -> None:
        keeper.on_app_change(clock())

    return on_pic, on_app
