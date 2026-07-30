---
# lg-tv-enhancer-9x3h
title: Keeper cannot distinguish its own write from a TV-initiated flip
status: completed
type: bug
priority: normal
created_at: 2026-07-30T03:36:18Z
updated_at: 2026-07-30T03:40:51Z
---

`lg-tv-enhancer-mtin` fixed the *startup* trigger (the on-subscribe app snapshot no longer arms a settle window), but the underlying weakness is untouched: the keeper judges a picture event purely by timing, so any write the daemon makes itself is indistinguishable from a flip the TV made.

Residual failure mode: a lux band commit that lands within `LGTV_SETTLE_SECS` (3s) of a *genuine* app switch is read as an app-induced flip and reverted. `poll_lux` has already recorded `applied_band` for that band and goes quiet (apply-once-per-band), so the TV stays on the wrong preset until the band next changes — the same latch as mtin, from a different trigger.

## Why it matters now

Gates dropping `LGTV_LUX_HOLD_SECS` to ~5 and `LGTV_LUX_POLL_SECS` to ~3. A short hold lets brief transients commit that a 30s hold filtered out (someone crossing the room, a phone near the sensor), and every extra commit is another chance to collide. Not poll rate itself — commit count is driven by real transitions, not polling.

Ruled out as a contributing factor: TV backlight spill. Measured 2026-07-29 with the screen Active on YouTube, forcing backlight 10 vs 90 moved the sensor 0.0 lux, so there is no optical feedback path inflating the commit rate.

## Fix directions

- Tag writes the daemon originates and let `on_picture_change` treat a matching echo as inert
- Or have `poll_lux` notice `keeper.current != applied_band` and re-apply — but this must NOT clobber a deliberate manual change, which is the whole point of the apply-once-per-band silence, so it needs the same origin-awareness anyway
- Regression test: real app switch, then a lux commit inside the settle window, assert no revert

- [x] Decide the origin-tracking mechanism
- [x] Implement with tests
- [x] Re-verify the mtin dark-room restart still passes

## Summary of Changes

The keeper now remembers the band each Correction it hands out should produce (`_issue`), and `on_picture_change` treats a matching picture event as its own echo: inert, even inside a settle window. Chose this over having `poll_lux` detect divergence and re-apply, because that path needs the same origin-awareness anyway and risks fighting deliberate manual changes.

Two details worth keeping in mind:

- The expectation is spent on the first picture event either way, matching how `_before` already disarms. A write that fails therefore cannot leave an expectation lingering to mask later corrections. Covered by a test.
- When an echo lands while a window is open, `_before` is refreshed to the newly written band. Otherwise the window would restore the stale pre-app-switch preset and undo a deliberate lux commit a moment later.

Tests: three keeper cases (commit inside the window is not reverted, the window then protects the lux band, a failed write does not swallow a later flip). 93 pass. Verified on the Pi with a dark-room restart at 23:40 — `ambient lux -> dark (0.0 lux)`, no restoring line, fingerprint read back as 85,10,50.

Not exercised live: the collision itself, which needs a lighting transition and an app switch within 3s of each other. It is covered by unit tests; contriving it on the TV was not attempted.
