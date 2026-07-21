"""Ambient-lux -> ISF band selection. Pure — no I/O, no clock, no hardware.

The sun daemon gets clean, rare transitions, so "apply once per phase" is free.
A lux sensor gives a jittery float many times a second; fed straight to a
threshold it flaps at every boundary (write storms, the TV visibly hunting when
a cloud passes). This module earns back the sun daemon's no-spam guarantee with
two guards, kept pure and testable like `sun.py`:

- **Spatial hysteresis:** the flip-to-Dark and flip-to-Bright edges differ, so a
  reading must cross the *far* edge to change bands, not merely wobble over the
  near one. Between the edges the current band is held.
- **Temporal debounce:** a new band must persist `hold_secs` before it commits,
  so a shadow or a phone-light sweep doesn't retint the room.

The caller threads `BandState` across ticks and applies the ISF preset only when
the committed `.band` changes — the lux analogue of "apply once per phase".
Thresholds are room- and mount-specific; see the README measurement notes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

DARK = "dark"
BRIGHT = "bright"


@dataclass(frozen=True)
class Bands:
    enter_dark_below: float    # flip to DARK once lux falls under this
    enter_bright_above: float  # flip to BRIGHT once lux rises over this
    hold_secs: float           # a new band must persist this long to commit


@dataclass(frozen=True)
class BandState:
    band: str                     # committed band the TV currently reflects
    pending: Optional[str]        # band awaiting debounce, or None if settled
    since: Optional[datetime]     # when `pending` first appeared


def _target(current: str, lux: float, bands: Bands) -> str:
    """Band the reading argues for, applying hysteresis (deadband holds current)."""
    if lux < bands.enter_dark_below:
        return DARK
    if lux > bands.enter_bright_above:
        return BRIGHT
    return current


def initial_state(lux: float, bands: Bands) -> BandState:
    """Cold-start band, applied immediately (no prior band to debounce against).

    In the deadband there is no history to hold, so default to BRIGHT rather than
    strand the viewer in Dark at boot.
    """
    return BandState(_target(BRIGHT, lux, bands), None, None)


def select_band(state: BandState, lux: float, now: datetime, bands: Bands) -> BandState:
    """Advance the selector one reading. Returns the (possibly unchanged) state.

    Commits a band change only after the new target has held for `hold_secs`; a
    reading that returns to the current band cancels an in-flight change.
    """
    target = _target(state.band, lux, bands)
    if target == state.band:
        return BandState(state.band, None, None)  # settled; drop any pending flip
    if state.pending != target:
        return BandState(state.band, target, now)  # new candidate; start the clock
    if now - state.since >= timedelta(seconds=bands.hold_secs):
        return BandState(target, None, None)       # held long enough; commit
    return state                                   # still counting down
