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
from datetime import datetime, timezone
from typing import Optional

from astral import Observer

import tv
from sun import NIGHT, current_phase

log = logging.getLogger("lg-tv-enhancer")

# Extra seconds slept past a transition so the next tick lands inside the new
# phase rather than on its boundary.
TRANSITION_SLACK = 2.0


@dataclass(frozen=True)
class Config:
    host: str
    key: Optional[str]
    lat: float
    lon: float
    poll_secs: float


def load_config(env=os.environ) -> Config:
    missing = [k for k in ("LGTV_HOST", "LGTV_LAT", "LGTV_LON") if not env.get(k)]
    if missing:
        raise SystemExit(f"missing required environment: {', '.join(missing)}")
    return Config(
        host=env["LGTV_HOST"],
        key=env.get("LGTV_KEY") or None,
        lat=float(env["LGTV_LAT"]),
        lon=float(env["LGTV_LON"]),
        poll_secs=float(env.get("LGTV_POLL_SECS", "60")),
    )


async def run(cfg: Config, *, apply=tv.apply_eye_comfort,
              clock=lambda: datetime.now(timezone.utc),
              sleep=asyncio.sleep) -> None:
    observer = Observer(latitude=cfg.lat, longitude=cfg.lon)
    applied_until: Optional[datetime] = None  # phase identity already applied
    failing = False                           # rate-limit: one warning per outage
    while True:
        now = clock()
        phase = current_phase(now, observer)
        desired = "on" if phase.kind == NIGHT else "off"
        if applied_until != phase.until:
            try:
                if await apply(cfg.host, cfg.key, desired):
                    applied_until = phase.until
                    if failing:
                        log.info("TV reachable again")
                        failing = False
                    log.info("eye comfort %s (%s until %s)",
                             desired, phase.kind, phase.until.isoformat())
                elif not failing:
                    log.warning("TV did not accept eyeComfortMode=%s; "
                                "retrying every %.0fs", desired, cfg.poll_secs)
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
