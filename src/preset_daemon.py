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
import sys
import time
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
ClientFactory = Callable[[str, str | None], Awaitable[object]]
Sleep = Callable[[float], Awaitable[None]]


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


CONNECT_TIMEOUT = 15.0
DISCONNECT_TIMEOUT = 5.0
HEARTBEAT_SECS = 30.0
RECONNECT_BACKOFF = 5.0
PING_INTERVAL = 30.0


async def _make_client(host: str, key: str | None) -> object:
    from bscpylgtv import WebOsClient  # lazy: tests run without the package
    return await WebOsClient.create(host, client_key=key, states=[],
                                    ping_interval=PING_INTERVAL)


async def _safe_disconnect(client) -> None:
    """Best-effort disconnect; a dead connection must not mask the real error."""
    try:
        await asyncio.wait_for(client.disconnect(), DISCONNECT_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - cleanup only, log and move on
        log.debug("disconnect failed (%s: %s)", type(exc).__name__, exc)


async def serve(cfg: Config, *, client_factory: ClientFactory = _make_client,
                clock: Callable[[], float] = time.monotonic,
                sleep: Sleep = asyncio.sleep) -> None:
    """One connection lifetime. Raises when the connection dies (heartbeat
    timeout / subscription error); the caller reconnects."""
    keeper = build_keeper(cfg)
    client = await asyncio.wait_for(client_factory(cfg.host, cfg.key), CONNECT_TIMEOUT)
    try:
        await asyncio.wait_for(client.connect(), CONNECT_TIMEOUT)
        on_pic, on_app = wire(keeper, client, clock=clock)
        # Picture first: its immediate on-subscribe push seeds the current preset
        # before any app-change event can arm a window.
        await asyncio.wait_for(client.subscribe_picture_settings(on_pic), REQUEST_TIMEOUT)
        await asyncio.wait_for(client.subscribe_current_app(on_app), REQUEST_TIMEOUT)
        log.info("preset keeper connected to %s", cfg.host)
        while True:
            await sleep(HEARTBEAT_SECS)
            # Liveness probe: a dead TV drops TCP without closing it, so an
            # unguarded call would hang. The timeout turns that into a reconnect.
            await asyncio.wait_for(client.get_current_app(), REQUEST_TIMEOUT)
    finally:
        await _safe_disconnect(client)


async def run(cfg: Config, *, serve: Callable[[Config], Awaitable[None]] = serve, sleep: Sleep = asyncio.sleep) -> None:
    failing = False
    while True:
        try:
            await serve(cfg)
            failing = False
        except Exception as exc:  # noqa: BLE001 - any failure means reconnect
            if not failing:
                log.warning("preset keeper connection lost (%s: %s); "
                            "reconnecting every %.0fs", type(exc).__name__, exc,
                            RECONNECT_BACKOFF)
                failing = True
        await sleep(RECONNECT_BACKOFF)


async def listen(cfg: Config, *, seconds: float = 120.0, client_factory: ClientFactory = _make_client) -> None:
    """Calibration: print each picture fingerprint and its classification.

    Flip through your presets (incl. a Dolby Vision title) and read off the
    tuples for LGTV_PRESET_BRIGHT / LGTV_PRESET_DARK. No writes.
    """
    from preset import classify, fingerprint_of

    client = await asyncio.wait_for(client_factory(cfg.host, cfg.key), CONNECT_TIMEOUT)
    await asyncio.wait_for(client.connect(), CONNECT_TIMEOUT)

    async def on_pic(settings: Mapping[str, object]) -> None:
        fp = fingerprint_of(settings)
        preset = classify(settings, bright=cfg.bright_fp, dark=cfg.dark_fp)
        print(f"fingerprint {fp} -> {preset}")

    try:
        await asyncio.wait_for(client.subscribe_picture_settings(on_pic), REQUEST_TIMEOUT)
        print(f"listening {seconds:.0f}s — flip your presets now")
        await asyncio.sleep(seconds)
    finally:
        await _safe_disconnect(client)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    cfg = load_config()
    if "--listen" in sys.argv:
        asyncio.run(listen(cfg))
        return
    log.info("preset keeper watching %s (bright=%s dark=%s, settle %.0fs)",
             cfg.host, cfg.bright_mode, cfg.dark_mode, cfg.settle_secs)
    try:
        asyncio.run(run(cfg))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
