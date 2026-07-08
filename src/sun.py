"""Day/night phase computation from sunset/sunrise. Pure — no I/O, no clock.

The daemon's unit of work is a *phase*: the span between two solar transitions
(sunrise -> day, sunset -> night). `current_phase` classifies a moment and
reports when the phase ends, so the caller can both decide the desired TV state
and use the end time as the phase's identity ("applied once per phase").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from astral import Observer
from astral.sun import elevation, sun

DAY = "day"
NIGHT = "night"

# Near the poles a date can have no sunrise/sunset at all. Rather than model
# polar seasons, classify by solar elevation and re-check a few hours later.
POLAR_RECHECK = timedelta(hours=6)


@dataclass(frozen=True)
class Phase:
    kind: str        # DAY or NIGHT
    until: datetime  # next transition (UTC); doubles as the phase's identity


def _events(observer: Observer, day) -> list[tuple[datetime, str]]:
    """Solar transitions on `day` as (time, phase-that-begins) pairs."""
    try:
        s = sun(observer, date=day, tzinfo=timezone.utc)
    except ValueError:  # polar day/night: sun never rises or never sets
        return []
    return [(s["sunrise"], DAY), (s["sunset"], NIGHT)]


def current_phase(now: datetime, observer: Observer) -> Phase:
    """Classify `now` (tz-aware) as day or night for `observer`'s location.

    Scans transitions over yesterday/today/tomorrow: the most recent past
    transition names the current phase; the next future one bounds it.
    """
    events: list[tuple[datetime, str]] = []
    for offset in (-1, 0, 1):
        events += _events(observer, (now + timedelta(days=offset)).date())
    events.sort()
    past = [e for e in events if e[0] <= now]
    future = [e for e in events if e[0] > now]
    if not past and not future:
        kind = DAY if elevation(observer, now) > 0 else NIGHT
        return Phase(kind, now + POLAR_RECHECK)
    if past:
        kind = past[-1][1]
    else:  # window edge: infer from what the next transition switches TO
        kind = NIGHT if future[0][1] == DAY else DAY
    until = future[0][0] if future else now + POLAR_RECHECK
    return Phase(kind, until)
