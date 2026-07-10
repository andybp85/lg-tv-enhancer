# Sticky ISF Preset Keeper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A second daemon that keeps the C9's ISF Bright/Dark preset sticky across app/input switches — when an app change flips you to the other ISF variant, it writes `pictureMode` back to the one you were on; Dolby Vision and everything else are left alone.

**Architecture:** Persistent webOS connection with two subscriptions (`subscribe_current_app`, `subscribe_picture_settings`). Presets are identified read-only by their slider **fingerprint** `(contrast, backlight, brightness)` because `pictureMode` is unreadable on this firmware; corrections are made by blind-writing `pictureMode` (trusted, like `eyeComfortMode`). A pure `Keeper` reducer holds the state machine; the daemon is thin I/O around it. Separate module and systemd service from the eye-comfort daemon (`main.py`/`tv.py`/`sun.py` untouched).

**Tech Stack:** Python 3 (async), `bscpylgtv` (already a dependency), `pytest`, systemd.

## Global Constraints

- **Python style:** full type annotations on every signature (params + return, incl. `-> None`); modern typing (`list[str]`, `tuple[int, int, int]`, `X | None`); dataclasses for structured data; 4-space indent; ≤140 columns.
- **Tests:** no `pytest-asyncio`. Drive async code via `asyncio.run(...)` wrappers, exactly like `tests/test_tv.py` and `tests/test_main.py`. `conftest.py` already puts `src/` on `sys.path`, so import modules by bare name (`from preset import ...`).
- **No new dependencies.** `bscpylgtv>=0.5.2` is already in `requirements.txt`.
- **Never write `contrast`/`backlight`/`brightness` to the TV — only `pictureMode`.** Those sliders are recognition values; the TV owns each preset's calibration.
- **Match fingerprints on the full `(contrast, backlight, brightness)` triple. Subset matching is a bug:** the sampled DV fingerprint `(90, 90, 60)` differs from Bright `(90, 90, 65)` only in brightness, so a backlight-only match would misread DV as Bright and fight Dolby Vision.
- **Reentrancy:** never `await` a TV request from inside a subscription callback — schedule the write with `asyncio.create_task`. Awaiting a request inside the callback deadlocks the client's consumer loop (it can't read the response while blocked in the callback).
- **Commit trailers:** end every commit message with the repo's two trailers (copy from `git log`):
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01EiHXXt6nq3FwupXv9eRgeJ
  ```

**Fingerprints (verified on the live C9), for reference across tasks:**

| preset | pictureMode | contrast | backlight | brightness |
|---|---|---|---|---|
| Bright | `expert1` | 90 | 90 | 65 |
| Dark | `expert2` | 85 | 10 | 50 |
| Dolby Vision (sampled) | — | 90 | 90 | 60 |

---

## File Structure

- `src/preset.py` — **pure logic**: preset constants, fingerprint parsing/classification, `Correction`, and the `Keeper` state machine. No I/O.
- `src/preset_daemon.py` — **I/O + entry point**: env config, connect/subscribe/reconnect loop, blind `pictureMode` writes, `--listen` calibration mode, `main()`.
- `tests/test_preset.py` — tests for the pure logic.
- `tests/test_preset_daemon.py` — tests for config loading and the callback wiring (with a fake client) and reconnect.
- `systemd/lg-tv-preset.service` — second systemd unit (shares `/etc/default/lg-tv-enhancer`).
- `systemd/lg-tv-enhancer.env.example` — **modify**: add the preset vars.
- `README.md` — **modify**: document the preset keeper, its config, and its deploy.

---

## Task 1: Fingerprint parsing and classification (`preset.py`)

**Files:**
- Create: `src/preset.py`
- Test: `tests/test_preset.py`

**Interfaces:**
- Produces:
  - `BRIGHT: str`, `DARK: str`, `UNKNOWN: str` — preset constants (values `"bright"`, `"dark"`, `"unknown"`).
  - `parse_fingerprint(csv: str) -> tuple[int, int, int]` — parse `"90,90,65"` → `(90, 90, 65)`; raises `ValueError` on wrong arity/non-int.
  - `fingerprint_of(settings: Mapping[str, object]) -> tuple[int, int, int] | None` — `(contrast, backlight, brightness)` from a picture-settings event (values arrive mixed `int`/`str`), or `None` if a key is missing/uncastable.
  - `classify(settings: Mapping[str, object], *, bright: tuple[int, int, int], dark: tuple[int, int, int]) -> str` — `BRIGHT` / `DARK` / `UNKNOWN`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_preset.py`:

```python
import pytest

from preset import (
    BRIGHT,
    DARK,
    UNKNOWN,
    classify,
    fingerprint_of,
    parse_fingerprint,
)

BRIGHT_FP = (90, 90, 65)
DARK_FP = (85, 10, 50)


def bright_settings() -> dict[str, object]:
    return {"contrast": 90, "backlight": 90, "brightness": 65, "color": "50"}


def dark_settings() -> dict[str, object]:
    # Deliberately mixed str/int, as the TV sends them.
    return {"contrast": "85", "backlight": 10, "brightness": "50", "color": "50"}


def dv_settings() -> dict[str, object]:
    return {"contrast": 90, "backlight": 90, "brightness": 60, "color": "50"}


def test_parse_fingerprint():
    assert parse_fingerprint("90,90,65") == (90, 90, 65)
    assert parse_fingerprint(" 85, 10 ,50 ") == (85, 10, 50)


def test_parse_fingerprint_rejects_wrong_arity():
    with pytest.raises(ValueError):
        parse_fingerprint("90,90")


def test_fingerprint_of_casts_mixed_types():
    assert fingerprint_of(dark_settings()) == (85, 10, 50)


def test_fingerprint_of_missing_key_returns_none():
    assert fingerprint_of({"contrast": 90, "backlight": 90}) is None


def test_classify_bright():
    assert classify(bright_settings(), bright=BRIGHT_FP, dark=DARK_FP) == BRIGHT


def test_classify_dark_with_string_values():
    assert classify(dark_settings(), bright=BRIGHT_FP, dark=DARK_FP) == DARK


def test_classify_dolby_vision_is_unknown():
    # DV (90,90,60) differs from Bright (90,90,65) only in brightness.
    assert classify(dv_settings(), bright=BRIGHT_FP, dark=DARK_FP) == UNKNOWN
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_preset.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'preset'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/preset.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_preset.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/preset.py tests/test_preset.py
git commit  # subject: "Preset: fingerprint parsing + classification"; include repo trailers
```

---

## Task 2: The `Keeper` state machine (`preset.py`)

**Files:**
- Modify: `src/preset.py`
- Test: `tests/test_preset.py`

**Interfaces:**
- Consumes: `BRIGHT`, `DARK`, `UNKNOWN`, `classify` from Task 1.
- Produces:
  - `Correction` — frozen dataclass: `mode: str` (the `pictureMode` value to write), `to_preset: str` (`BRIGHT`/`DARK`, for logging).
  - `Keeper` — constructed with `bright_fp`, `dark_fp`, `bright_mode`, `dark_mode`, `settle_secs` (all keyword). Methods:
    - `on_picture_change(settings: Mapping[str, object], now: float) -> Correction | None`
    - `on_app_change(now: float) -> None`

  Semantics: `on_app_change` snapshots the current preset and arms a settle window (`now + settle_secs`). The first `on_picture_change` after that — if within the window and it flipped from one ISF variant to the *other* — returns a `Correction` back to the pre-switch preset, then disarms. Picture events outside any window just update the tracked current preset (a manual change). `now` is monotonic seconds.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_preset.py`:

```python
from preset import Correction, Keeper


def make_keeper() -> Keeper:
    return Keeper(bright_fp=BRIGHT_FP, dark_fp=DARK_FP,
                  bright_mode="expert1", dark_mode="expert2", settle_secs=3.0)


def test_app_flip_bright_to_dark_restores_bright():
    k = make_keeper()
    assert k.on_picture_change(bright_settings(), now=0.0) is None  # seed current = bright
    k.on_app_change(now=10.0)
    correction = k.on_picture_change(dark_settings(), now=10.5)
    assert correction == Correction(mode="expert1", to_preset=BRIGHT)


def test_app_flip_dark_to_bright_restores_dark():
    k = make_keeper()
    k.on_picture_change(dark_settings(), now=0.0)
    k.on_app_change(now=10.0)
    correction = k.on_picture_change(bright_settings(), now=10.2)
    assert correction == Correction(mode="expert2", to_preset=DARK)


def test_same_preset_after_app_change_no_correction():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    k.on_app_change(now=10.0)
    # No mode change means no picture event fires; nothing to correct. If the TV
    # does re-emit the same fingerprint, it must not trigger a write.
    assert k.on_picture_change(bright_settings(), now=10.3) is None


def test_manual_change_without_app_change_is_not_corrected():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    # User deliberately flips Bright -> Dark with no app switch: no correction,
    # and Dark becomes the new sticky value.
    assert k.on_picture_change(dark_settings(), now=100.0) is None
    k.on_app_change(now=101.0)
    correction = k.on_picture_change(bright_settings(), now=101.2)
    assert correction == Correction(mode="expert2", to_preset=DARK)


def test_app_change_into_dolby_vision_is_left_alone():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    k.on_app_change(now=5.0)
    assert k.on_picture_change(dv_settings(), now=5.3) is None  # after = UNKNOWN


def test_coming_from_dolby_vision_is_left_alone():
    k = make_keeper()
    k.on_picture_change(dv_settings(), now=0.0)  # current = UNKNOWN
    k.on_app_change(now=5.0)
    assert k.on_picture_change(dark_settings(), now=5.2) is None  # before = UNKNOWN


def test_picture_event_after_window_expiry_is_manual():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    k.on_app_change(now=10.0)  # window closes at 13.0
    assert k.on_picture_change(dark_settings(), now=20.0) is None


def test_corrective_write_event_does_not_loop():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    k.on_app_change(now=10.0)
    assert k.on_picture_change(dark_settings(), now=10.5) is not None  # correction issued
    # The write flips the TV back to bright, producing this event; must be inert.
    assert k.on_picture_change(bright_settings(), now=10.6) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_preset.py -q`
Expected: FAIL — `ImportError: cannot import name 'Correction'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/preset.py`:

```python
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

    def __init__(self, *, bright_fp: tuple[int, int, int], dark_fp: tuple[int, int, int],
                 bright_mode: str, dark_mode: str, settle_secs: float) -> None:
        self._bright_fp = bright_fp
        self._dark_fp = dark_fp
        self._mode = {BRIGHT: bright_mode, DARK: dark_mode}
        self._settle_secs = settle_secs
        self._current = UNKNOWN
        self._before: str | None = None   # preset snapshot at the last app change
        self._deadline = 0.0              # settle-window end (monotonic)

    def on_app_change(self, now: float) -> None:
        self._before = self._current
        self._deadline = now + self._settle_secs

    def on_picture_change(self, settings: Mapping[str, object], now: float) -> Correction | None:
        after = classify(settings, bright=self._bright_fp, dark=self._dark_fp)
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_preset.py -q`
Expected: PASS (15 passed).

- [ ] **Step 5: Commit**

```bash
git add src/preset.py tests/test_preset.py
git commit  # subject: "Preset: Keeper state machine (correct app-switch ISF flips)"; repo trailers
```

---

## Task 3: Config loading (`preset_daemon.py`)

**Files:**
- Create: `src/preset_daemon.py`
- Test: `tests/test_preset_daemon.py`

**Interfaces:**
- Consumes: `parse_fingerprint` from `preset`.
- Produces:
  - `Config` — frozen dataclass: `host: str`, `key: str | None`, `bright_fp: tuple[int, int, int]`, `dark_fp: tuple[int, int, int]`, `bright_mode: str`, `dark_mode: str`, `settle_secs: float`.
  - `load_config(env: Mapping[str, str] = os.environ) -> Config` — requires `LGTV_HOST`; defaults `LGTV_PRESET_BRIGHT=90,90,65`, `LGTV_PRESET_DARK=85,10,50`, `LGTV_MODE_BRIGHT=expert1`, `LGTV_MODE_DARK=expert2`, `LGTV_SETTLE_SECS=3`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_preset_daemon.py`:

```python
import pytest

from preset_daemon import Config, load_config


def test_load_config_requires_host():
    with pytest.raises(SystemExit):
        load_config(env={})


def test_load_config_defaults():
    cfg = load_config(env={"LGTV_HOST": "tv"})
    assert cfg.key is None
    assert cfg.bright_fp == (90, 90, 65)
    assert cfg.dark_fp == (85, 10, 50)
    assert cfg.bright_mode == "expert1"
    assert cfg.dark_mode == "expert2"
    assert cfg.settle_secs == 3.0


def test_load_config_custom_fingerprints_and_modes():
    cfg = load_config(env={
        "LGTV_HOST": "tv",
        "LGTV_KEY": "abc",
        "LGTV_PRESET_BRIGHT": "88,92,66",
        "LGTV_PRESET_DARK": "80,5,48",
        "LGTV_MODE_BRIGHT": "expert2",
        "LGTV_MODE_DARK": "expert1",
        "LGTV_SETTLE_SECS": "5",
    })
    assert cfg.key == "abc"
    assert cfg.bright_fp == (88, 92, 66)
    assert cfg.dark_fp == (80, 5, 48)
    assert cfg.bright_mode == "expert2"
    assert cfg.settle_secs == 5.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_preset_daemon.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'preset_daemon'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/preset_daemon.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_preset_daemon.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/preset_daemon.py tests/test_preset_daemon.py
git commit  # subject: "Preset daemon: env config"; repo trailers
```

---

## Task 4: Callback wiring and the guarded write (`preset_daemon.py`)

**Files:**
- Modify: `src/preset_daemon.py`
- Test: `tests/test_preset_daemon.py`

**Interfaces:**
- Consumes: `Config` (Task 3); `Keeper`, `Correction` from `preset`.
- Produces:
  - `build_keeper(cfg: Config) -> Keeper`
  - `REQUEST_TIMEOUT: float`
  - `wire(keeper: Keeper, client, *, clock, spawn=asyncio.create_task) -> tuple[callback, callback]` — returns `(on_pic, on_app)` async callbacks. `on_pic` runs the keeper and, on a `Correction`, schedules the write via `spawn` (never awaits inside the callback — reentrancy). `on_app` arms the keeper.
  - `async _guarded_write(client, mode: str) -> None` — `await client.set_settings("picture", {"pictureMode": mode})` under `REQUEST_TIMEOUT`, logging success/failure, never raising.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_preset_daemon.py`:

```python
import asyncio

from preset_daemon import build_keeper, wire


class FakeClient:
    """Records pictureMode writes; stands in for bscpylgtv's WebOsClient."""

    def __init__(self) -> None:
        self.set_calls: list[dict[str, object]] = []

    async def set_settings(self, category: str, settings: dict[str, object]) -> None:
        assert category == "picture"
        self.set_calls.append(settings)


CFG = Config(host="tv", key="k", bright_fp=(90, 90, 65), dark_fp=(85, 10, 50),
             bright_mode="expert1", dark_mode="expert2", settle_secs=3.0)


def _bright() -> dict[str, object]:
    return {"contrast": 90, "backlight": 90, "brightness": 65, "color": "50"}


def _dark() -> dict[str, object]:
    return {"contrast": 85, "backlight": 10, "brightness": 50, "color": "50"}


def _dv() -> dict[str, object]:
    return {"contrast": 90, "backlight": 90, "brightness": 60, "color": "50"}


def test_wire_writes_pictureMode_on_app_flip():
    async def scenario():
        client = FakeClient()
        keeper = build_keeper(CFG)
        t = [0.0]
        on_pic, on_app = wire(keeper, client, clock=lambda: t[0])
        await on_pic(_bright())          # seed current = bright
        t[0] = 10.0
        await on_app("netflix")
        t[0] = 10.5
        await on_pic(_dark())            # TV flipped to dark -> correct
        await asyncio.sleep(0)           # let the spawned write task run
        assert client.set_calls == [{"pictureMode": "expert1"}]

    asyncio.run(scenario())


def test_wire_leaves_dolby_vision_alone():
    async def scenario():
        client = FakeClient()
        keeper = build_keeper(CFG)
        t = [0.0]
        on_pic, on_app = wire(keeper, client, clock=lambda: t[0])
        await on_pic(_bright())
        t[0] = 5.0
        await on_app("disneyplus")
        t[0] = 5.3
        await on_pic(_dv())              # DV -> UNKNOWN -> hands off
        await asyncio.sleep(0)
        assert client.set_calls == []

    asyncio.run(scenario())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_preset_daemon.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_keeper'`.

- [ ] **Step 3: Write the minimal implementation**

Replace the entire top-of-file import block of `src/preset_daemon.py` (everything from `from __future__` down to the `from preset import ...` line) with:

```python
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping

from preset import Correction, Keeper, parse_fingerprint
```

Add after `load_config`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_preset_daemon.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/preset_daemon.py tests/test_preset_daemon.py
git commit  # subject: "Preset daemon: callback wiring + guarded pictureMode write"; repo trailers
```

---

## Task 5: Connection loop, reconnect, `--listen`, and entry point (`preset_daemon.py`)

**Files:**
- Modify: `src/preset_daemon.py`
- Test: `tests/test_preset_daemon.py`

**Interfaces:**
- Consumes: `Config`, `build_keeper`, `wire`, `REQUEST_TIMEOUT` (Task 4); `classify`, `fingerprint_of` from `preset`.
- Produces:
  - `async serve(cfg, *, client_factory=_make_client, clock=time.monotonic, sleep=asyncio.sleep) -> None` — one connection lifetime: connect, subscribe (picture **first** to seed current preset, then current app), then a timeout-guarded heartbeat loop that returns/raises when the connection dies. Always disconnects.
  - `async run(cfg, *, serve=serve, sleep=asyncio.sleep) -> None` — reconnect forever with `RECONNECT_BACKOFF`, one warning per outage.
  - `async listen(cfg, *, seconds=120.0, client_factory=_make_client) -> None` — calibration: print each picture fingerprint and its classification, no writes.
  - `main() -> None` — logging + config; `--listen` runs `listen`, else `run`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_preset_daemon.py`:

```python
from preset_daemon import run


class StopLoop(Exception):
    pass


def test_run_reconnects_after_serve_failure():
    async def scenario():
        attempts = []

        async def flaky_serve(cfg):
            attempts.append(1)
            raise ConnectionResetError("connection dropped")

        ticks = [0]

        async def sleep(secs):
            ticks[0] += 1
            if ticks[0] >= 3:
                raise StopLoop

        with pytest.raises(StopLoop):
            await run(CFG, serve=flaky_serve, sleep=sleep)
        assert len(attempts) == 3  # serve retried each time the backoff elapsed

    asyncio.run(scenario())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `venv/bin/pytest tests/test_preset_daemon.py::test_run_reconnects_after_serve_failure -q`
Expected: FAIL — `ImportError: cannot import name 'run'`.

- [ ] **Step 3: Write the minimal implementation**

Add `import sys` and `import time` to the top-of-file imports of `src/preset_daemon.py` (alongside the existing `import asyncio` / `import logging` / `import os`).

Append to `src/preset_daemon.py`:

```python
CONNECT_TIMEOUT = 15.0
DISCONNECT_TIMEOUT = 5.0
HEARTBEAT_SECS = 30.0
RECONNECT_BACKOFF = 5.0
PING_INTERVAL = 30.0


async def _make_client(host: str, key: str | None):
    from bscpylgtv import WebOsClient  # lazy: tests run without the package
    return await WebOsClient.create(host, client_key=key, states=[],
                                    ping_interval=PING_INTERVAL)


async def serve(cfg: Config, *, client_factory=_make_client,
                clock: Callable[[], float] = time.monotonic,
                sleep=asyncio.sleep) -> None:
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
        try:
            await asyncio.wait_for(client.disconnect(), DISCONNECT_TIMEOUT)
        except Exception:
            pass


async def run(cfg: Config, *, serve=serve, sleep=asyncio.sleep) -> None:
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


async def listen(cfg: Config, *, seconds: float = 120.0, client_factory=_make_client) -> None:
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
        await client.subscribe_picture_settings(on_pic)
        print(f"listening {seconds:.0f}s — flip your presets now")
        await asyncio.sleep(seconds)
    finally:
        try:
            await asyncio.wait_for(client.disconnect(), DISCONNECT_TIMEOUT)
        except Exception:
            pass


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
```

- [ ] **Step 4: Run the full suite**

Run: `venv/bin/pytest -q`
Expected: PASS — the pre-existing eye-comfort tests plus all new `test_preset*.py` tests (26+ passed, 0 failed).

- [ ] **Step 5: Commit**

```bash
git add src/preset_daemon.py tests/test_preset_daemon.py
git commit  # subject: "Preset daemon: connect/subscribe/reconnect loop, --listen, entry point"; repo trailers
```

---

## Task 6: systemd unit, env template, and README

**Files:**
- Create: `systemd/lg-tv-preset.service`
- Modify: `systemd/lg-tv-enhancer.env.example`
- Modify: `README.md`

**Interfaces:** none (ops + docs).

- [ ] **Step 1: Create the systemd unit**

Create `systemd/lg-tv-preset.service` (mirrors `lg-tv-enhancer.service`; shares the same root-owned env file — same TV host/key):

```ini
[Unit]
Description=LG TV ISF preset keeper (hold Bright/Dark across app/input switches)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
# Adjust user/paths to your Pi account before installing.
User=pi
WorkingDirectory=/home/pi/lg-tv-enhancer
ExecStart=/home/pi/lg-tv-enhancer/venv/bin/python src/preset_daemon.py
Restart=on-failure
RestartSec=5
Environment=LOG_LEVEL=INFO
Environment=PYTHONUNBUFFERED=1
# Shares the eye-comfort daemon's config file (same TV, same pairing key). The
# preset vars (LGTV_PRESET_BRIGHT/DARK, LGTV_MODE_*, LGTV_SETTLE_SECS) are
# optional and default to the calibrated C9 values. See the env example.
EnvironmentFile=-/etc/default/lg-tv-enhancer

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Extend the env template**

Append to `systemd/lg-tv-enhancer.env.example`:

```bash

# --- ISF preset keeper (lg-tv-preset.service) ---------------------------------
# Presets are recognized by their picture-settings fingerprint
# "contrast,backlight,brightness" (the C9 won't report pictureMode by name).
# Defaults are the calibrated C9 values; re-derive with:
#   /home/pi/lg-tv-enhancer/venv/bin/python src/preset_daemon.py --listen
#LGTV_PRESET_BRIGHT=90,90,65
#LGTV_PRESET_DARK=85,10,50

# pictureMode value written to restore each preset.
#LGTV_MODE_BRIGHT=expert1
#LGTV_MODE_DARK=expert2

# Seconds after an app/input change to still attribute a mode change to it.
#LGTV_SETTLE_SECS=3
```

- [ ] **Step 3: Update the README**

In `README.md`, update the `src/` tree and add a "Preset keeper" section. Replace the tree block:

```
src/
├── main.py          # eye-comfort reconcile loop + env config
├── sun.py           # pure day/night phase computation (astral)
├── tv.py            # eyeComfortMode get/set via bscpylgtv, timeout-guarded
├── preset.py        # pure ISF preset classification + Keeper state machine
└── preset_daemon.py # ISF preset keeper: subscribe to app + picture, correct
```

Add this section after the eye-comfort "How it works" section:

```markdown
## ISF preset keeper (second daemon)

The C9 remembers the last picture mode **per app/input**, but ISF Bright/Dark is
really a *global* choice (room light), not a per-app one. `preset_daemon.py`
holds a persistent webOS connection and, when an app/input switch flips you to
the other ISF variant, writes `pictureMode` back to the one you were on.

- `pictureMode` is **unreadable** on this firmware (same whitelist refusal as
  `eyeComfortMode`), so presets are recognized by their picture-settings
  **fingerprint** `(contrast, backlight, brightness)`, pushed over
  `subscribe_picture_settings`. Corrections are blind `pictureMode` writes.
- **Unknown fingerprint → hands off.** Dolby Vision, Cinema, Game, and any
  customized preset are left alone — no enumeration needed. (Sampled DV
  `(90,90,60)` sits one brightness point from Bright `(90,90,65)`, which is why
  matching uses the full triple.)
- **Manual Bright↔Dark** (no app switch) is respected and becomes the new
  sticky value.

Calibrate or re-derive fingerprints (prints each mode's tuple as you flip):

\`\`\`bash
venv/bin/python src/preset_daemon.py --listen
\`\`\`

Config lives in the same env file as the eye-comfort daemon; see the table below.
```

Add the preset vars to the configuration table in `README.md`:

```markdown
| `LGTV_PRESET_BRIGHT` / `LGTV_PRESET_DARK` | `90,90,65` / `85,10,50` | ISF preset fingerprints `contrast,backlight,brightness` |
| `LGTV_MODE_BRIGHT` / `LGTV_MODE_DARK` | `expert1` / `expert2` | pictureMode written to restore each preset |
| `LGTV_SETTLE_SECS` | `3` | app-change → mode-settle window |
```

Add a note under the Deploy section that the second service installs the same way:

```markdown
The preset keeper is a second unit installed the same way:

\`\`\`bash
sudo cp systemd/lg-tv-preset.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lg-tv-preset
journalctl -u lg-tv-preset -f
\`\`\`
```

- [ ] **Step 4: Verify the suite still passes and docs render**

Run: `venv/bin/pytest -q`
Expected: PASS (unchanged from Task 5 — docs/systemd don't affect tests).

- [ ] **Step 5: Commit**

```bash
git add systemd/lg-tv-preset.service systemd/lg-tv-enhancer.env.example README.md
git commit  # subject: "Preset keeper: systemd unit, env template, README"; repo trailers
```

---

## Post-implementation: live verification on the Pi

Not a code task — do this after deploy (rsync per README), with the user:

1. `--listen` on the Pi; flip Bright → Dark → Bright and confirm the printed
   classifications match; play a DV title and confirm it prints `-> unknown`.
2. With `lg-tv-preset` running: on ISF Bright, switch between two apps that
   remember *different* ISF variants; confirm it snaps back to Bright within the
   settle window, and that a DV title is left alone.
3. Watch `journalctl -u lg-tv-preset -f` for `restored pictureMode=…` lines and
   for any unexpected `unknown` fingerprints (would reveal a mis-set config
   tuple or an uncatalogued DV mode).

## Spec coverage check

- Core rule (restore pre-switch ISF variant) → Task 2 (`Keeper`).
- DV / unknown hands-off, both directions → Tasks 1–2 (`classify` UNKNOWN + `_evaluate`), tested.
- Manual change becomes sticky → Task 2 test `test_manual_change_without_app_change_is_not_corrected`.
- Observe app + picture; blind-write pictureMode; reentrancy-safe → Tasks 4–5.
- Exact full-triple match / no subset match → Task 1 + Global Constraints.
- Seed on reconnect (picture subscribed first) → Task 5 `serve`.
- Timeout-guarded, reconnect with backoff → Task 5.
- Config (env vars, defaults) → Task 3.
- `--listen` calibration + unknown logging → Task 5 (`listen`) + Task 4 (`_guarded_write`/classify logging path); README documents it.
- Separate service, eye-comfort untouched → Task 6; no edits to `main.py`/`tv.py`/`sun.py`.
```
