---
# lg-tv-enhancer-80lc
title: Cold start in the deadband should leave the preset alone
status: completed
type: bug
priority: normal
created_at: 2026-07-30T10:34:17Z
updated_at: 2026-07-30T10:37:18Z
---

`initial_state` defaults to BRIGHT when the cold-start reading sits between the band edges, on the rationale of not stranding the viewer in Dark at boot. That guess is wrong more often than it is right:

- It only ever fires in the deadband — the one place we cannot tell which band is correct. A genuinely bright room reads above the edge and applies Bright without the default.
- The preset already on the TV is real information: it is whatever the last committed band or the viewer chose. Overriding it with a constant discards that.
- It jumps the backlight to 90 on any restart during dawn, dusk, or a dim room.

Observed 2026-07-30: raising `LGTV_LUX_BRIGHT_ABOVE` from 3.0 to 7.0 (the old value was calibrated while the sensor was blinded and read 2.5 in a lit room) widened the deadband from 1–3 to 1–7. The very next restart logged `ambient lux -> bright (3.3 lux)` — committing Bright at less than half the threshold it was meant to respect.

## Change

In the deadband, commit to neither band: `BandState.band` becomes None until a reading crosses an edge. `poll_lux` then writes nothing, because its `state.band != applied_band` guard is already False when both are None.

Note the invariant: once a band is committed, `_target` returns the current band inside the deadband, so `band` can never return to None. It is a startup-only state.

- [x] Replace the test asserting the old default
- [x] Uncommitted start stays uncommitted in the deadband, commits on a real crossing
- [x] Verify no write on a deadband restart on the Pi

## Summary of Changes

`initial_state` now passes None as the hysteresis "current" instead of BRIGHT, so a cold-start reading inside the deadband commits to neither band. `poll_lux` needed no change: its `state.band != applied_band` guard is already False when both are None, so it writes nothing and stays quiet until a reading crosses an edge.

`BandState.band` and `_target` widened to `Optional[str]`. The invariant that keeps this from leaking: once a band is committed, `_target` holds it through the deadband, so `band` can never return to None. It is a startup-only state, documented on `initial_state`.

Replaced `test_cold_start_in_deadband_defaults_bright`, which asserted the behavior being removed. Added four band-level cases (deadband commits to neither, stays uncommitted while ambiguous, commits Bright when light arrives, commits Dark when it goes) and two `poll_lux`-level cases proving no write happens and that it is not stuck. The no-write test was confirmed failing against the old one-argument default. 108 pass.

## Verified on the Pi, better than planned

The 06:19 restart had written `expert1` at 3.3 lux — the bug. Between then and 06:36 the user set the TV back to Dark by hand; the journal shows no daemon write, so the keeper correctly adopted it. The 06:36 restart with the fix, at 5.0 lux in the now-wider 1–7 deadband, logged no band line at all and left the fingerprint at `85,10,50`.

So the fix was verified protecting a *deliberate manual preference*, which is a stronger case than the inferred-band one the bean was written around: the old code would have overwritten a hand-picked preset on every restart in ambiguous light.

Context: the edges themselves were also wrong. `LGTV_LUX_BRIGHT_ABOVE` was calibrated while the sensor was blinded (2.5 lux in a lit room) and was never re-derived after the sensor moved, so 3.0 sat below dawn ambient. Raised to 7.0 against a lit-room reading of 8.3 — a single sample, so a 24h log is running at `~/lux-24h.csv` on the Pi to confirm the headroom.
