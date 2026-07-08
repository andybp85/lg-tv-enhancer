"""lg-tv-enhancer: engage the TV's Eye Comfort Mode from sunset to sunrise.

Reconcile loop, not a scheduler: every tick it computes the desired state from
the sun's phase and applies it once per phase. That shape gives three
behaviors for free:

- TV off at sunset -> the change lands on the first tick after the TV is back.
- TV never spammed: a phase is applied once, then left alone.
- Manual override respected: turning the mode off by hand at night holds until
  the next transition (we don't re-assert mid-phase).

Config is env-only (12-factor); see systemd/lg-tv-enhancer.env.example.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from astral import Observer

import tv
from sun import NIGHT, current_phase, night_factor

log = logging.getLogger("lg-tv-enhancer")

# Extra seconds slept past a transition so the next tick lands inside the new
# phase rather than on its boundary.
TRANSITION_SLACK = 2.0


# C9 colorTemperature slider bounds: negative = warm, positive = cool.
CT_RANGE = (-50, 50)


@dataclass(frozen=True)
class Config:
    host: str
    key: Optional[str]
    lat: float
    lon: float
    poll_secs: float
    ct_night: Optional[int]  # None = circadian color temperature off
    ct_day: int
    ct_ramp_mins: float


def load_config(env=os.environ) -> Config:
    missing = [k for k in ("LGTV_HOST", "LGTV_LAT", "LGTV_LON") if not env.get(k)]
    if missing:
        raise SystemExit(f"missing required environment: {', '.join(missing)}")
    ct_night = int(env["LGTV_CT_NIGHT"]) if env.get("LGTV_CT_NIGHT") else None
    ct_day = int(env.get("LGTV_CT_DAY", "0"))
    for name, value in (("LGTV_CT_NIGHT", ct_night), ("LGTV_CT_DAY", ct_day)):
        if value is not None and not CT_RANGE[0] <= value <= CT_RANGE[1]:
            raise SystemExit(f"{name}={value} outside colorTemperature range "
                             f"{CT_RANGE[0]}..{CT_RANGE[1]}")
    return Config(
        host=env["LGTV_HOST"],
        key=env.get("LGTV_KEY") or None,
        lat=float(env["LGTV_LAT"]),
        lon=float(env["LGTV_LON"]),
        poll_secs=float(env.get("LGTV_POLL_SECS", "60")),
        ct_night=ct_night,
        ct_day=ct_day,
        ct_ramp_mins=float(env.get("LGTV_CT_RAMP_MINS", "45")),
    )


def ct_target(cfg: Config, now: datetime, phase) -> Optional[int]:
    """Color temperature the ramp wants right now; None when the feature is
    off. Quantized to the slider's integer steps, so consecutive ticks inside
    a flat stretch produce the same value and trigger no write."""
    if cfg.ct_night is None:
        return None
    f = night_factor(now, phase, timedelta(minutes=cfg.ct_ramp_mins))
    return round(cfg.ct_day + (cfg.ct_night - cfg.ct_day) * f)


async def run(cfg: Config, *, apply=tv.apply_eye_comfort,
              apply_settings=tv.apply_picture_settings,
              clock=lambda: datetime.now(timezone.utc),
              sleep=asyncio.sleep) -> None:
    observer = Observer(latitude=cfg.lat, longitude=cfg.lon)
    applied_until: Optional[datetime] = None  # phase identity already applied
    applied_ct: Optional[int] = None          # last color temperature written
    failing = False                           # rate-limit: one warning per outage

    def recovered() -> None:
        nonlocal failing
        if failing:
            log.info("TV reachable again")
            failing = False

    while True:
        now = clock()
        phase = current_phase(now, observer)
        desired = "on" if phase.kind == NIGHT else "off"
        target = ct_target(cfg, now, phase)
        try:
            if applied_until != phase.until:
                if await apply(cfg.host, cfg.key, desired):
                    applied_until = phase.until
                    recovered()
                    log.info("eye comfort %s (%s until %s)",
                             desired, phase.kind, phase.until.isoformat())
                elif not failing:
                    log.warning("TV did not accept eyeComfortMode=%s; "
                                "retrying every %.0fs", desired, cfg.poll_secs)
                    failing = True
            if target is not None and target != applied_ct:
                if await apply_settings(cfg.host, cfg.key,
                                        {"colorTemperature": str(target)}):
                    applied_ct = target
                    recovered()
                    log.info("color temperature -> %d", target)
                elif not failing:
                    log.warning("TV did not accept colorTemperature=%d; "
                                "retrying every %.0fs", target, cfg.poll_secs)
                    failing = True
        except Exception as exc:
            if not failing:
                log.warning("TV unreachable (%s: %s); retrying every %.0fs "
                            "(suppressing repeats)", type(exc).__name__,
                            exc, cfg.poll_secs)
                failing = True
        delay = min(cfg.poll_secs,
                    max(1.0, (phase.until - now).total_seconds() + TRANSITION_SLACK))
        await sleep(delay)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    cfg = load_config()
    log.info("watching sun at (%.4f, %.4f); TV at %s; poll %.0fs",
             cfg.lat, cfg.lon, cfg.host, cfg.poll_secs)
    try:
        asyncio.run(run(cfg))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
