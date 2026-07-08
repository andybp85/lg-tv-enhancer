---
# lg-tv-enhancer-o84i
title: Slim repo to the eye comfort scheduler; remove exploration scripts
status: completed
type: task
priority: normal
created_at: 2026-07-08T10:24:57Z
updated_at: 2026-07-08T10:25:28Z
---

Picture-mode exploration concluded (DV mode list is firmware-fixed; nothing to enable). Remove scripts/force-picture-mode.py and scripts/tv-status.py plus their README section — the deliverable is the sunset-to-sunrise daemon only. Scripts remain recoverable from git history (2cc84d8, db7ba08). Redeploy to the Pi with --delete so they disappear there too.

## Summary of Changes
- Deleted scripts/force-picture-mode.py and scripts/tv-status.py (recoverable at 2cc84d8 / db7ba08).
- Removed README Scripts section.
- 20 tests still green; daemon untouched.
