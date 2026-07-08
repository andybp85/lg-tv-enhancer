---
# lg-tv-enhancer-2l83
title: 'scripts/force-picture-mode.py: apply picture mode to all inputs x dynamic ranges'
status: completed
type: task
priority: normal
created_at: 2026-07-08T09:07:33Z
updated_at: 2026-07-08T09:08:29Z
---

One-off CLI that forces picture modes into every input x dynamic-range slot on the C9 via bscpylgtv set_picture_mode (luna scoped category picture$<input>.x.2d.<dr>). Default mode map per dynamic range, positional dr=mode overrides, --inputs/--dry-run, read-back verification where the firmware supports it. Caveat noted: scoped-category syntax documented against newer models (C3); verify one slot first.

## Summary of Changes
- scripts/force-picture-mode.py: sweeps picture modes across all inputs x dynamic ranges via set_picture_mode, default mode map + dr=mode overrides, --inputs/--dry-run/--host/--key, per-slot read-back verification (confirmed/blind/rejected summary), timeout-guarded awaits.
- README: Scripts section with usage and the verify-one-slot-first caveat.
- No unit tests: ops script whose only logic (override parsing, plan expansion) is exercised by --dry-run; correctness is verified live by read-back.
