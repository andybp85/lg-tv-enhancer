---
# lg-tv-enhancer-rokq
title: 'scripts/tv-status.py: inputs, foreground app, current picture mode'
status: completed
type: task
priority: normal
created_at: 2026-07-08T10:06:23Z
updated_at: 2026-07-08T10:07:14Z
---

Pasteable heredoc failed over ssh (sudo prompt ate lines), and the user wants to check what picture mode Netflix runs in. Add a status script: external input list (id/label/icon/connected), foreground appId, best-effort current pictureMode via getSystemSettings (may be firmware-refused like eyeComfortMode, lg-tv-enhancer-ccuj). Env from LGTV_HOST/LGTV_KEY like the other script.

## Summary of Changes
- scripts/tv-status.py: inputs (id/label/icon/connected), foreground appId, best-effort current pictureMode (graceful message when the firmware whitelist refuses the read). Timeout-guarded; env like the other scripts.
- README: Scripts section entry.
