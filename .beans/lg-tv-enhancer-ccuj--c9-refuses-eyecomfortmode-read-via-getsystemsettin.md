---
# lg-tv-enhancer-ccuj
title: C9 refuses eyeComfortMode read via getSystemSettings; daemon never applies
status: completed
type: bug
priority: normal
created_at: 2026-07-08T09:57:55Z
updated_at: 2026-07-08T09:59:01Z
---

Live deploy: connect + pairing OK, but get_picture_settings(keys=["eyeComfortMode"]) fails with '500 Application error ... Some keys are not allowed for the request. ( eyeComfortMode )'. The C9's ssap getSystemSettings whitelists readable keys; eyeComfortMode is write-only (luna set_settings path). apply_eye_comfort raised on the read, so the daemon warned 'TV unreachable' every phase and never wrote.

Fix: treat a refused read as 'unverifiable' (None) instead of an error — skip the current-value shortcut, write via luna set_settings, and trust the write when read-back is unavailable. Timeouts still propagate (dead connection => retry). Also add PYTHONUNBUFFERED=1 to the unit so bscpylgtv's stdout prints land in journald in real time.

## Todo
- [x] tv.py: refused read -> blind write; keep timeout propagation
- [x] tests: blind-write path
- [x] systemd: PYTHONUNBUFFERED=1

## Summary of Changes
- tv.py: _read_mode returns None when the firmware refuses the key (C9: write-only via ssap GET); apply_eye_comfort then skips the matching shortcut, writes via luna set_settings, and trusts the write. asyncio.TimeoutError still propagates so a dead connection retries instead of degrading to blind.
- tests: blind-write success path + write failure during blind mode still raises (20 tests green).
- systemd unit: PYTHONUNBUFFERED=1 so bscpylgtv stdout prints land in journald in real time.
