---
# lg-tv-enhancer-ulp5
title: 'Reconnect loop is undiagnosable: silent when DNS fails, 876 lines/24h when it doesn''t'
status: completed
type: bug
priority: normal
created_at: 2026-07-26T04:34:49Z
updated_at: 2026-07-30T10:00:36Z
---

Two opposite logging failures around the same path in `src/preset_daemon.py`.

**Silent.** `run()` warns only on the first failure (the `failing` flag, :256-260). When `LGTV_HOST` fails name resolution, bscpylgtv never reaches a socket attempt, so it prints nothing either. Result on 2026-07-26: ~1h of zero output while the lux hook was entirely down — indistinguishable from healthy-and-dark, since `poll_lux` is transition-only by design.

**Deafening.** When the name does resolve and the TV refuses, bscpylgtv logs `Connection attempt: N` at default level — 876 lines in 24h, burying the daemon's own INFO lines.

Note `poll_lux` is spawned inside `serve()` (:222) and cancelled in its `finally` (:237-240), so no TV connection means no lux polling at all. It self-heals on reconnect (`state=None` -> `initial_state` -> applies on first poll), so this is a diagnosability bug, not a functional one.

- [x] Periodic heartbeat while reconnecting, so a down hook is visible in the journal
- [x] ~~Demote the bscpylgtv logger to WARNING~~ — wrong premise, see below
- [x] Assert the heartbeat in tests with a fake clock

Related: [[lg-tv-enhancer-g5bm]] removes the DNS trigger but not the blind spot.

## Summary of Changes

**The logger todo was based on a wrong premise.** Those lines are bare `print()` calls in `bscpylgtv/webos_client.py` (lines 211 and 755), not logging — there is no logger to demote, and no verbosity flag guards them. Our own logs also go to `sys.stdout`, so `StandardOutput=null` in the unit would have silenced us too.

Fixed at the source instead: `_make_client` now passes `connect_retry_attempts=1`, which makes the librarys `attempt < attempts - 1` guard never true so the print never fires. It also removes a redundant retry layer — 9 internal attempts at 200ms nested inside `run`s own 5s reconnect loop. One retry policy, and it lives in `run`. Cost: a transient blip now surfaces immediately and waits ~5s for our loop instead of being papered over in ~1.8s.

**Heartbeat**: `run` takes a clock and restates the outage every `DOWN_HEARTBEAT_SECS` (300s), naming the thing the silence hid — that the lux hook is not polling — plus elapsed time, attempt count, and the last error.

**Latent bug found while implementing.** `serve` never returns normally (its `while True` has no break), so `failing = False` in `run` was unreachable and the flag latched True: only the *first* disconnect in a process lifetime was ever reported. `serve` now signals a successful connect through an `on_up` callback, which resets the outage state, so every drop warns. This was almost certainly compounding the silence observed on 2026-07-26.

Verified on the Pi: normal restart connects and arms as usual; a throwaway instance pointed at an unroutable RFC 5737 TEST-NET-1 address for 40s produced exactly one warning and zero `Connection attempt` lines, where the old code would have printed ~56.

Deferred to [[lg-tv-enhancer-qm9f]]: the warning renders as `connection lost (TimeoutError: )` because `asyncio.TimeoutError` carries no message. qm9f rewrites these lines for its error taxonomy, so the formatting fix belongs there rather than being done twice.
