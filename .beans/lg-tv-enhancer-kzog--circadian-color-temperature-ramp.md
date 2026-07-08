---
# lg-tv-enhancer-kzog
title: Circadian color temperature ramp
status: completed
type: feature
priority: normal
created_at: 2026-07-08T10:39:30Z
updated_at: 2026-07-08T11:09:41Z
---

Graduated version of the eye comfort daemon: instead of (or alongside) the binary sunset/sunrise flip, ramp the picture colorTemperature warmer through the evening and back at dawn, f.lux-style.

Notes from the eye comfort work:
- colorTemperature is in the same "picture" settings category (C9 doc shows it as a numeric string, observed "-50"; range needs confirming — likely -50..50).
- Reads may be firmware-refused like eyeComfortMode was (lg-tv-enhancer-ccuj) — plan for blind writes.
- Fits the existing reconcile loop: sun.py already yields phase + next transition; a ramp needs elevation-or-time-based interpolation and a smaller write cadence (e.g. every 10-15 min during the ramp window, not per-tick).
- Decide interaction with manual override: per-step blind writes would fight a user adjustment all evening unless the ramp also applies once-per-step.

## Summary of Changes
- sun.py: Phase gains `since` (phase start); new pure `night_factor(now, phase, ramp)` — 0..1 linear ramp after each transition, flat elsewhere.
- tv.py: generalized to `apply_picture_settings(host, key, settings)` (string-compared values, same refused-read->blind-write semantics); `apply_eye_comfort` is now a thin wrapper.
- main.py: `ct_target` quantizes day->night interpolation to integer slider steps; loop writes only on step change, shares the once-per-outage warning rate limit. Config: LGTV_CT_NIGHT (enables, -50..50 validated), LGTV_CT_DAY (0), LGTV_CT_RAMP_MINS (45).
- Manual-override semantics preserved: writes only during ramp windows / on step change; flat stretches never re-assert.
- Caveat documented: colorTemperature is per picture mode; a mode switch mid-night keeps that mode's own temp until the next step write or transition.
- Tests: 29 green (ramp factor invariants, string comparison, once-per-step writes, monotonic ramp across a real sunset, config validation).
- README + env.example updated; feature is off unless LGTV_CT_NIGHT is set, so existing deploys are unaffected.
