"""Keep the C9's ISF Bright/Dark preset sticky across app/input switches.

`pictureMode` is unreadable on this firmware (the getSystemSettings whitelist
refuses it, same as eyeComfortMode — lg-tv-enhancer-ccuj), so presets are
identified by their picture-settings slider *fingerprint* (contrast, backlight,
brightness). Any fingerprint that matches neither ISF preset is UNKNOWN, and
UNKNOWN means hands off — which is what keeps Dolby Vision safe without
enumerating its modes. This module is pure: no I/O, no clock of its own.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

BRIGHT = "bright"
DARK = "dark"
UNKNOWN = "unknown"

_KEYS = ("contrast", "backlight", "brightness")


def parse_fingerprint(csv: str) -> tuple[int, int, int]:
    """Parse a 'contrast,backlight,brightness' config value into a triple."""
    parts = [int(p.strip()) for p in csv.split(",")]
    if len(parts) != 3:
        raise ValueError(f"expected 3 comma-separated ints, got {csv!r}")
    return (parts[0], parts[1], parts[2])


def parse_fingerprints(csv: str) -> frozenset[tuple[int, int, int]]:
    """Parse one or more ';'-separated fingerprints into a set.

    A preset needs several fingerprints because the C9 stores picture settings
    *per input*: ISF Bright/Dark read different slider values on an HDMI input
    than on the built-in apps (e.g. Bright is (90,90,65) on an app but
    (90,100,60) on the cable box). Any of a preset's fingerprints identifies it.
    """
    return frozenset(parse_fingerprint(part) for part in csv.split(";"))


def fingerprint_of(settings: Mapping[str, object]) -> tuple[int, int, int] | None:
    """(contrast, backlight, brightness) from a picture-settings event.

    The TV sends these values as a mix of int and str; cast them. Returns None
    when any of the three keys is absent or uncastable.
    """
    try:
        return tuple(int(settings[k]) for k in _KEYS)  # type: ignore[arg-type,return-value]
    except (KeyError, TypeError, ValueError):
        return None


def classify(settings: Mapping[str, object], *,
             bright: frozenset[tuple[int, int, int]],
             dark: frozenset[tuple[int, int, int]]) -> str:
    """BRIGHT / DARK / UNKNOWN by exact match against a preset's fingerprints.

    Exact full-triple membership keeps the UNKNOWN=hands-off guarantee tight:
    Dolby Vision (90,90,60) matches none of the ISF fingerprints even though it
    sits one brightness point from an app's Bright (90,90,65).
    """
    fp = fingerprint_of(settings)
    if fp in bright:
        return BRIGHT
    if fp in dark:
        return DARK
    return UNKNOWN


@dataclass(frozen=True)
class Correction:
    """A pictureMode write to re-impose the pre-switch ISF preset."""
    mode: str        # pictureMode value to write, e.g. "expert1"
    to_preset: str   # BRIGHT or DARK — for logging


class Keeper:
    """State machine: correct an app-switch-induced ISF flip, ignore the rest.

    Fed a stream of app-change and picture-change events (with a monotonic
    clock). An app change arms a short settle window; the first picture change
    inside it that flipped from one ISF variant to the other yields a Correction
    back to the pre-switch preset. Everything else — manual changes, Dolby
    Vision, unknown presets, late events — updates the tracked preset only.
    """

    def __init__(self, *, bright_fps: frozenset[tuple[int, int, int]],
                 dark_fps: frozenset[tuple[int, int, int]],
                 bright_mode: str, dark_mode: str, settle_secs: float) -> None:
        self._bright_fps = bright_fps
        self._dark_fps = dark_fps
        self._mode = {BRIGHT: bright_mode, DARK: dark_mode}
        self._settle_secs = settle_secs
        self._current = UNKNOWN
        self._before: str | None = None   # preset snapshot at the last app change
        self._deadline = 0.0              # settle-window end (monotonic)

    def on_app_change(self, now: float) -> None:
        self._before = self._current
        self._deadline = now + self._settle_secs

    def on_picture_change(self, settings: Mapping[str, object], now: float) -> Correction | None:
        after = classify(settings, bright=self._bright_fps, dark=self._dark_fps)
        correction = None
        if self._before is not None:
            if now <= self._deadline:
                correction = self._evaluate(self._before, after)
            self._before = None  # disarm on the first picture event, in or out of window
        self._current = after
        return correction

    def _evaluate(self, before: str, after: str) -> Correction | None:
        variants = (BRIGHT, DARK)
        if before in variants and after in variants and before != after:
            return Correction(mode=self._mode[before], to_preset=before)
        return None
