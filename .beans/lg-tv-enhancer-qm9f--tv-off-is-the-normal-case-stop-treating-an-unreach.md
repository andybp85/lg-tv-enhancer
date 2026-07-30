---
# lg-tv-enhancer-qm9f
title: TV-off is the normal case; stop treating an unreachable TV as an error
status: completed
type: task
priority: low
created_at: 2026-07-26T04:35:00Z
updated_at: 2026-07-30T10:06:53Z
blocked_by:
    - lg-tv-enhancer-ulp5
---

`run()` in `src/preset_daemon.py` funnels every failure through one `except Exception` -> "preset keeper connection lost", including the most common and least alarming state: the TV is simply off. A powered-down TV is expected for most of any given day and should not read as a fault.

Worth distinguishing:
- **TV off / connection refused / timeout** — normal, log at INFO or debug, keep retrying quietly
- **Name resolution failure** — config problem worth a real warning (an IP in `LGTV_HOST` can't fail this way; see [[lg-tv-enhancer-g5bm]])
- **Auth/pairing rejection** — actionable, warn loudly; retrying won't fix a bad key

Depends on the shape chosen in [[lg-tv-enhancer-ulp5]]; do that first so the heartbeat and these levels are designed together.

- [x] Decide the taxonomy and log level per class
- [x] Implement, keeping `run()`'s reconnect-forever contract intact
- [x] Tests per class with an injected failing `serve`

## Summary of Changes

Four classes, not the three planned — a fourth was needed so a bug cannot hide among the expected failures:

| Class | Level | Covers |
|---|---|---|
| `FAILURE_NORMAL` | INFO | off, refused, reset, unreachable, timed out |
| `FAILURE_CONFIG` | WARNING | `LGTV_HOST` does not resolve |
| `FAILURE_AUTH` | ERROR | pairing rejected; retrying cannot help |
| `FAILURE_UNEXPECTED` | WARNING | anything else, including our own bugs |

That last one earned its place during this work: a test fake with a stale signature raised `TypeError`, which `run`'s catch-all reported as a lost connection. Without a distinct class it would now be filed at INFO as probably-the-TV-is-off.

Implementation notes:

- `classify_failure` is pure and matches the auth type **by class name**, not `isinstance`, so importing bscpylgtv stays lazy — the suite runs without the package.
- `socket.gaierror` is checked before the errno branch; it subclasses `OSError` and its `EAI_*` codes collide numerically with unrelated errnos.
- A change of failure class mid-outage logs immediately instead of waiting out the heartbeat. The 2026-07-26 incident went refused -> unresolvable while the TV stayed reachable by IP, and that transition was the whole diagnosis. Verified by temporarily removing the branch and watching the test fail.
- Picked up the formatting fix deferred from [[lg-tv-enhancer-ulp5]]: `_describe` falls back to a `message` attribute, because `asyncio.TimeoutError` carries no message **and** every bscpylgtv exception sets `self.message` without calling `super().__init__`. Previously an auth failure would have logged as `PyLGTVPairException: ` with the reason discarded.

Verified on the Pi: an unroutable address logs INFO `TV unreachable (TimeoutError)`, a bogus hostname logs WARNING `cannot resolve LGTV_HOST=...`. 103 tests pass. README gained a table for reading the levels.

Not verified live: the auth class. Forcing it needs a bad `LGTV_KEY`, which puts a pairing dialog on the screen — not worth doing to someone else's TV for a path already covered by unit tests.
