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
import contextlib
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Mapping

from lux import Bands, initial_state, select_band
from luxsource import LuxSource, make_source
from preset import Correction, Keeper, parse_fingerprints


@dataclass(frozen=True)
class Config:
    host: str
    key: str | None
    bright_fps: frozenset[tuple[int, int, int]]
    dark_fps: frozenset[tuple[int, int, int]]
    bright_mode: str
    dark_mode: str
    settle_secs: float
    # Ambient-lux hook (inert unless LGTV_LUX_SOURCE selects a source). Defaults
    # measured in-room; see the README ambient-light section (7f7w).
    lux_poll_secs: float
    lux_dark_below: float
    lux_bright_above: float
    lux_hold_secs: float


def load_config(env: Mapping[str, str] = os.environ) -> Config:
    if not env.get("LGTV_HOST"):
        raise SystemExit("missing required environment: LGTV_HOST")
    try:
        return Config(
            host=env["LGTV_HOST"],
            key=env.get("LGTV_KEY") or None,
            bright_fps=parse_fingerprints(env.get("LGTV_PRESET_BRIGHT", "90,90,65")),
            dark_fps=parse_fingerprints(env.get("LGTV_PRESET_DARK", "85,10,50")),
            bright_mode=env.get("LGTV_MODE_BRIGHT", "expert1"),
            dark_mode=env.get("LGTV_MODE_DARK", "expert2"),
            settle_secs=float(env.get("LGTV_SETTLE_SECS", "3")),
            lux_poll_secs=float(env.get("LGTV_LUX_POLL_SECS", "30")),
            lux_dark_below=float(env.get("LGTV_LUX_DARK_BELOW", "1.0")),
            lux_bright_above=float(env.get("LGTV_LUX_BRIGHT_ABOVE", "3.0")),
            lux_hold_secs=float(env.get("LGTV_LUX_HOLD_SECS", "30")),
        )
    except ValueError as exc:
        raise SystemExit(f"invalid preset config: {exc}")


log = logging.getLogger("lg-tv-preset")

REQUEST_TIMEOUT = 10.0

Callback = Callable[..., Awaitable[None]]
ClientFactory = Callable[[str, str | None], Awaitable[object]]
Sleep = Callable[[float], Awaitable[None]]

# asyncio keeps only a weak reference to a bare create_task() result, so a
# fire-and-forget task can be garbage-collected before it finishes (dropping
# the correction). Hold a strong ref until the task completes.
_pending_writes: set[asyncio.Task[None]] = set()


def _spawn_tracked(coro: Awaitable[None]) -> asyncio.Task[None]:
    task = asyncio.create_task(coro)
    _pending_writes.add(task)
    task.add_done_callback(_pending_writes.discard)
    return task


def build_keeper(cfg: Config) -> Keeper:
    return Keeper(bright_fps=cfg.bright_fps, dark_fps=cfg.dark_fps,
                  bright_mode=cfg.bright_mode, dark_mode=cfg.dark_mode,
                  settle_secs=cfg.settle_secs)


async def _guarded_write(client, mode: str) -> bool:
    """Blind-write pictureMode, logging the outcome. Never raises: it runs either
    as a detached task (app-flip correction) or awaited by the lux loop, and
    neither wants an unhandled error. Returns True on a confirmed write so the
    lux loop knows whether to retry."""
    try:
        await asyncio.wait_for(
            client.set_settings("picture", {"pictureMode": mode}), REQUEST_TIMEOUT)
        log.info("wrote pictureMode=%s", mode)
        return True
    except Exception as exc:  # noqa: BLE001 - detached/awaited, log and move on
        log.warning("preset write failed (%s: %s)", type(exc).__name__, exc)
        return False


def wire(keeper: Keeper, client, *, clock: Callable[[], float],
         spawn: Callable[[Awaitable[None]], object] = _spawn_tracked) -> tuple[Callback, Callback]:
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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def poll_lux(source: LuxSource, keeper: Keeper, client, cfg: Config, *,
                   clock: Callable[[], datetime] = _utc_now,
                   sleep: Sleep = asyncio.sleep) -> None:
    """Reconcile the ISF preset to room brightness. Runs beside the keeper's
    subscriptions on the same connection, so there is one writer of pictureMode.

    Reads lux, debounces it into a band (`lux.select_band`), and drives the
    keeper only when the committed band *changes* — apply-once-per-band, the lux
    twin of the sun loop. That silence between crossings is what lets a manual
    Bright/Dark ride until the light next crosses a band. A failed write or an
    UNKNOWN preset (Dolby Vision) is left un-applied and retried next poll; an
    already-correct TV is marked applied so we go quiet.
    """
    bands = Bands(cfg.lux_dark_below, cfg.lux_bright_above, cfg.lux_hold_secs)
    state = None
    applied_band: str | None = None
    failing = False
    while True:
        try:
            lux = await asyncio.wait_for(source.read(), REQUEST_TIMEOUT)
            if failing:
                log.info("lux sensor reading again")
                failing = False
        except Exception as exc:  # noqa: BLE001 - sensor blips must not kill the loop
            if not failing:
                log.warning("lux read failed (%s: %s); retrying every %.0fs",
                            type(exc).__name__, exc, cfg.lux_poll_secs)
                failing = True
            await sleep(cfg.lux_poll_secs)
            continue
        state = (initial_state(lux, bands) if state is None
                 else select_band(state, lux, clock(), bands))
        if state.band != applied_band:
            correction = keeper.set_desired(state.band)
            if correction is not None:
                if await _guarded_write(client, correction.mode):
                    log.info("ambient lux -> %s (%.1f lux)", state.band, lux)
                    applied_band = state.band
                # else: write failed; leave un-applied to retry next poll
            elif keeper.current == state.band:
                applied_band = state.band  # already there; go quiet
            # else: current is UNKNOWN (e.g. Dolby Vision); defer, retry next poll
        await sleep(cfg.lux_poll_secs)


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


async def serve(cfg: Config, *, source: LuxSource | None = None,
                client_factory: ClientFactory = _make_client,
                clock: Callable[[], float] = time.monotonic,
                lux_clock: Callable[[], datetime] = _utc_now,
                sleep: Sleep = asyncio.sleep) -> None:
    """One connection lifetime. Raises when the connection dies (heartbeat
    timeout / subscription error); the caller reconnects. With a lux `source`,
    an ambient poll task runs on this same connection and is torn down with it."""
    keeper = build_keeper(cfg)
    client = await asyncio.wait_for(client_factory(cfg.host, cfg.key), CONNECT_TIMEOUT)
    lux_task: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(client.connect(), CONNECT_TIMEOUT)
        on_pic, on_app = wire(keeper, client, clock=clock)
        # Picture first: its immediate on-subscribe push seeds the current preset
        # before any app-change event can arm a window — and before the lux task
        # can ask the keeper what's on.
        await asyncio.wait_for(client.subscribe_picture_settings(on_pic), REQUEST_TIMEOUT)
        # The immediate current-app push on subscribe arms a settle window here;
        # harmless in steady state (no picture event follows, so it expires as
        # "manual"). Picture is subscribed first above so _current is seeded.
        await asyncio.wait_for(client.subscribe_current_app(on_app), REQUEST_TIMEOUT)
        log.info("preset keeper connected to %s", cfg.host)
        if source is not None:
            lux_task = asyncio.create_task(
                poll_lux(source, keeper, client, cfg, clock=lux_clock, sleep=sleep))
            log.info("ambient lux hook active (dark<%.1f bright>%.1f, hold %.0fs, "
                     "poll %.0fs)", cfg.lux_dark_below, cfg.lux_bright_above,
                     cfg.lux_hold_secs, cfg.lux_poll_secs)
        while True:
            await sleep(HEARTBEAT_SECS)
            # A crash in the lux task (not a mere sensor blip, which it swallows)
            # surfaces here as a reconnect rather than a silent dead hook.
            if lux_task is not None and lux_task.done():
                lux_task.result()
            # Liveness probe: a dead TV drops TCP without closing it, so an
            # unguarded call would hang. The timeout turns that into a reconnect.
            await asyncio.wait_for(client.get_current_app(), REQUEST_TIMEOUT)
    finally:
        if lux_task is not None:
            lux_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lux_task
        await _safe_disconnect(client)


async def run(cfg: Config, *, source: LuxSource | None = None,
              serve: Callable[..., Awaitable[None]] = serve,
              sleep: Sleep = asyncio.sleep) -> None:
    """Reconnect forever. Owns the lux source's lifetime (closed on exit); the
    per-connection lux task is spawned inside `serve`."""
    failing = False
    try:
        while True:
            try:
                await serve(cfg, source=source)
                failing = False
            except Exception as exc:  # noqa: BLE001 - any failure means reconnect
                if not failing:
                    log.warning("preset keeper connection lost (%s: %s); "
                                "reconnecting every %.0fs", type(exc).__name__,
                                exc, RECONNECT_BACKOFF)
                    failing = True
            await sleep(RECONNECT_BACKOFF)
    finally:
        if source is not None:
            await source.close()


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
        preset = classify(settings, bright=cfg.bright_fps, dark=cfg.dark_fps)
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
    source = make_source()
    log.info("preset keeper watching %s (bright=%s dark=%s, settle %.0fs)%s",
             cfg.host, cfg.bright_mode, cfg.dark_mode, cfg.settle_secs,
             "" if source is None else "; ambient lux hook enabled")
    try:
        asyncio.run(run(cfg, source=source))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
