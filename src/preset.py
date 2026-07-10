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


def fingerprint_of(settings: Mapping[str, object]) -> tuple[int, int, int] | None:
    """(contrast, backlight, brightness) from a picture-settings event.

    The TV sends these values as a mix of int and str; cast them. Returns None
    when any of the three keys is absent or uncastable.
    """
    try:
        return tuple(int(settings[k]) for k in _KEYS)  # type: ignore[arg-type,return-value]
    except (KeyError, TypeError, ValueError):
        return None


def classify(settings: Mapping[str, object], *, bright: tuple[int, int, int],
             dark: tuple[int, int, int]) -> str:
    """BRIGHT / DARK / UNKNOWN by exact match on the full slider triple."""
    fp = fingerprint_of(settings)
    if fp == bright:
        return BRIGHT
    if fp == dark:
        return DARK
    return UNKNOWN
