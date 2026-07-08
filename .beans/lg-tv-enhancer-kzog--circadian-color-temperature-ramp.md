---
# lg-tv-enhancer-kzog
title: Circadian color temperature ramp
status: todo
type: feature
priority: deferred
created_at: 2026-07-08T10:39:30Z
updated_at: 2026-07-08T11:13:02Z
---

Graduated version of the eye comfort daemon: instead of (or alongside) the binary sunset/sunrise flip, ramp the picture colorTemperature warmer through the evening and back at dawn, f.lux-style.

Notes from the eye comfort work:
- colorTemperature is in the same "picture" settings category (C9 doc shows it as a numeric string, observed "-50"; range needs confirming — likely -50..50).
- Reads may be firmware-refused like eyeComfortMode was (lg-tv-enhancer-ccuj) — plan for blind writes.
- Fits the existing reconcile loop: sun.py already yields phase + next transition; a ramp needs elevation-or-time-based interpolation and a smaller write cadence (e.g. every 10-15 min during the ramp window, not per-tick).
- Decide interaction with manual override: per-step blind writes would fight a user adjustment all evening unless the ramp also applies once-per-step.

## Deferred (2026-07-08)
Implemented and parked on branch `circadian-ct` (commit 9c33b25, tests green) — not merged because webOS keys colorTemperature PER PICTURE MODE, and the user switches isf Dark <-> Bright by hand: the ramp would only ever land on whichever mode is active, leaving the other stale. Binary eyeComfortMode covers the need without that problem.

To revive: merge the branch, then solve per-mode fan-out — either write the temp to all modes the user actually uses (set_picture_settings per mode slot), or watch the active mode and re-apply on change.
