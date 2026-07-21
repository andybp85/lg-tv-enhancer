---
# lg-tv-enhancer-7f7w
title: 'Explore: external ambient-light-sensor hook to auto-drive ISF preset / picture brightness'
status: in-progress
type: feature
priority: normal
created_at: 2026-07-14T02:05:34Z
updated_at: 2026-07-21T02:35:02Z
---

Explore an external ambient-light-sensor hook that drives the TV's ISF preset (or picture brightness) automatically. The C9's built-in light sensor is **not** exposed over the webOS SSAP LAN API (bscpylgtv) — it only feeds the TV's internal Energy Saving / Eye Comfort features; no lux reading is readable or subscribable. So any light-adaptive behavior must come from an **external** sensor on the Pi, with the daemon reacting by pushing picture state to the TV.

Exploratory only — capturing design direction, not committing to build.

## Shape: the sun daemon with a different phase function

`main.py` is a reconcile loop whose brain is `sun.current_phase(now) -> Phase(kind, until)`. A lux hook is the same loop with the sun swapped for a sensor read:

    sun.current_phase(now, observer)  ->  lux_band(read_lux(), state)

Everything else in `run()` carries over: ephemeral connect/reconcile/disconnect, timeout guards, apply-once-per-phase, manual-override-respected. Reuses `tv.py`'s write path.

## The one genuinely new problem: lux is noisy + continuous

The sun gives clean, rare transitions, so "apply once per phase" is free. A lux sensor gives a jittery float many times/sec — feed it straight to a band-selector and it flaps at every boundary (write storms; TV visibly hunting when a cloud passes). The real design work is a **debounced band selector with hysteresis**, kept pure/testable like `sun.py`:

- **Spatial hysteresis:** overlapping band bounds (deadband) — must cross the *far* edge to flip, not the near one.
- **Temporal debounce:** a band must hold N seconds before it counts, so a flashlight sweep doesn't retint the room.

That pairing earns back the sun daemon's "no spam" guarantee.

## The edge: a pluggable reader (isolate I/O)

Keep the sensor behind a tiny `LuxSource` protocol (`async read() -> float`) so the daemon doesn't care whether it's I2C or HTTP, and tests inject a fake. Candidate sources: BH1750 / TSL2591 over I2C on the Pi; Home Assistant / MQTT lux value; a file (testing). Source picked by env (12-factor): `LGTV_LUX_SOURCE=bh1750|http|file`.

## The real decision: coexistence with the ISF preset keeper

The preset keeper (`preset_daemon.py`) exists because ISF Bright/Dark is a *room-light choice made by hand*, kept sticky across app switches. A lux hook is that same choice automated — so they overlap, not independent.

- **Option A (preferred) — lux drives the keeper's target.** Lux band picks Bright vs Dark; the keeper enforces it across inputs. One writer of `pictureMode`, no fighting. Manual Bright<->Dark = temporary override until lux crosses a band.
- **Option B — lux writes a continuous slider** (OLED Light / backlight) inside whichever ISF preset is active, independent of Bright/Dark. Finer-grained, but two daemons now write picture settings and can step on each other.

Lean **A**: reuses the existing keeper, single owner of `pictureMode`.

## Adjacent work

Related to `lg-tv-enhancer-kzog` (circadian color-temperature ramp) — that's the warmth axis, this is the brightness axis. Same "environment drives picture" engine; could share the reconcile loop.

## Open questions

- [x] Which sensor / source (I2C BH1750 vs Home Assistant vs MQTT)? → **BH1750FVI over I2C**, acquired 2026-07-19 (ACEIRMC 3-pack, 5V-labeled breakout)
- [x] Option A vs B → **Option A** (decided 2026-07-19): lux band picks ISF Bright vs Dark, the preset keeper enforces it. Single writer of `pictureMode`; manual Bright<->Dark is a temporary override until lux crosses a band.
- [ ] Band thresholds (lux -> dark/dim/bright) and hysteresis widths — needs real measurement in the room
- [x] Debounce hold time — **30s**. The band edge sits at 1–3 lux (bottom of range), where a drastic change is almost always a deliberate lamp switch (a sustained step), not a slow dusk ramp — so the debounce only rejects transients (shadow ~2s, headlight sweep a few s, phone glance ~10–30s). 30s covers those and keeps lamp-off near-instant. If a dark-room phone glance ever flips to Bright, escape hatch is an asymmetric hold (fast to Dark, slow to Bright).
- [ ] Does this merge with, or run beside, the circadian-color-temp daemon?

## Hardware (decided 2026-07-19)

BH1750FVI breakout, I2C, 3-pack. Wiring/mounting notes:

- **Power from the Pi's 3.3V pin, not 5V.** The board is sold as "DC 5V" but the Pi's GPIO/I2C lines are 3.3V-only; running VCC at 5V risks pulling SDA/SCL above 3.3V and damaging the Pi. BH1750 runs fine at 3.3V.
- Pins: VCC → 3v3, GND → GND, SDA → GPIO2, SCL → GPIO3. ADDR floating/GND = address `0x23`; ADDR high = `0x5C` (only matters for a second sensor on the bus).
- Board ships with **male** header pins → needs female-to-female jumpers to reach the Pi header.
- **Mounting: the sensor must sit outside the Pi enclosure.** It needs line of sight to room light; inside an opaque box it reads ~0 lux and is subject to the same limitation as the TV's built-in sensor. Run it on a short lead through a grommet/hole and mount the photodiode facing the room (not the TV — avoid the panel's own output feeding back into the band selector).
- Driver: `adafruit-circuitpython-bh1750` or plain `smbus2` behind the `LuxSource` protocol; env `LGTV_LUX_SOURCE=bh1750`.

Band thresholds still need real measurement in the room once mounted.

ADDR left floating → I2C address `0x23`. Verify with `sudo raspi-config nonint do_i2c 0` then `i2cdetect -y 1`.

**Watch the pin order:** the module silkscreen reads VCC / SCL / DAT / GND / ADDR — SCL and SDA are swapped relative to the header order (SDA=GPIO2 pin 3, SCL=GPIO3 pin 5).

Header pins used: 1 (3v3), 3 (GPIO2/SDA), 5 (GPIO3/SCL), 9 (GND).

## Measurement stage (2026-07-19)

Sensor wired and enumerating at `0x23`. Root cause of the initial empty `i2cdetect` scan: DAT landed on header pin 4 (5V rail) instead of pin 3 (GPIO2). The module survived it.

Landed:

- `src/bh1750.py` — one-shot high-res read over I2C. Raw 2-byte transfer via `i2c_rdwr`, since the BH1750 has no register address and `read_i2c_block_data` would prepend a command byte the chip reads as an instruction.
- `tools/log_lux.py` — appends timestamped lux to CSV, flushed per row.
- `tests/test_bh1750.py` — decode + read path against a fake bus; no hardware needed.
- README section: wiring table, the SCL/DAT silkscreen trap, mounting constraint, logging command.

Next: run the logger through a full day/night cycle in the room, then pick band thresholds and hysteresis widths from the CSV.

## Band selector landed (2026-07-20)

`src/lux.py` — pure `select_band(state, lux, now, bands) -> BandState`, same shape as `sun.py`. Spatial hysteresis (deadband holds current band) + temporal debounce (`hold_secs` before commit). Caller applies the ISF preset only when committed `.band` changes = the lux analogue of "apply once per phase". `tests/test_lux.py`, 10 tests. Full suite 63 passed.

Thresholds are mount-specific — sensor is behind the TV. Moving it means re-measuring.

Still open: wire `lux.py` + `bh1750.py` into a daemon that drives the preset keeper's target (Option A), and the merge-vs-coexist question with the circadian daemon (`lg-tv-enhancer-kzog`).

## Daemon wiring landed (2026-07-20) — Option A wired

Folded the lux hook into the preset keeper (single writer of pictureMode), all TDD, default-off via `LGTV_LUX_SOURCE`:

- `src/luxsource.py` — `LuxSource` protocol + `BH1750Source` (blocking I2C read in `asyncio.to_thread`), `FileSource` (HA/MQTT bridge or tests), `make_source` env factory. `tests/test_luxsource.py` (9).
- `src/preset.py` — `Keeper.set_desired(band)` returns the write needed, or None when already there / UNKNOWN (Dolby Vision stays hands-off, even for lux). Added `current` property. `tests/test_preset.py` +5.
- `src/preset_daemon.py` — `poll_lux()` reconcile loop: reads lux, `select_band`, drives the keeper only on a committed band *change* (apply-once-per-band → manual override rides until the next crossing). Failed write / UNKNOWN preset deferred + retried; already-correct TV goes quiet. Spawned inside `serve()` on the same connection, torn down with it. Config gains `LGTV_LUX_*`. `tests/test_preset_daemon.py` +10 (startup, blip-ignore, hold-commit, already-on-band, DV-defer, DV-ends-applies, manual-override-rides, write-retry).

Full suite 86 passed. Docs updated: README ambient-light section rewritten (hook, not just measurement), config table rows, env example.

Remaining open: merge-vs-coexist with the circadian color-temp daemon (`lg-tv-enhancer-kzog`).
