---
# lg-tv-enhancer-qm9f
title: TV-off is the normal case; stop treating an unreachable TV as an error
status: todo
type: task
priority: low
created_at: 2026-07-26T04:35:00Z
updated_at: 2026-07-26T04:35:05Z
blocked_by:
    - lg-tv-enhancer-ulp5
---

`run()` in `src/preset_daemon.py` funnels every failure through one `except Exception` -> "preset keeper connection lost", including the most common and least alarming state: the TV is simply off. A powered-down TV is expected for most of any given day and should not read as a fault.

Worth distinguishing:
- **TV off / connection refused / timeout** — normal, log at INFO or debug, keep retrying quietly
- **Name resolution failure** — config problem worth a real warning (an IP in `LGTV_HOST` can't fail this way; see [[lg-tv-enhancer-g5bm]])
- **Auth/pairing rejection** — actionable, warn loudly; retrying won't fix a bad key

Depends on the shape chosen in [[lg-tv-enhancer-ulp5]]; do that first so the heartbeat and these levels are designed together.

- [ ] Decide the taxonomy and log level per class
- [ ] Implement, keeping `run()`'s reconnect-forever contract intact
- [ ] Tests per class with an injected failing `serve`
