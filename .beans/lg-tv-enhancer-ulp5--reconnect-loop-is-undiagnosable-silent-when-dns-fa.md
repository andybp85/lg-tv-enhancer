---
# lg-tv-enhancer-ulp5
title: 'Reconnect loop is undiagnosable: silent when DNS fails, 876 lines/24h when it doesn''t'
status: todo
type: bug
priority: normal
created_at: 2026-07-26T04:34:49Z
updated_at: 2026-07-26T04:34:49Z
---

Two opposite logging failures around the same path in `src/preset_daemon.py`.

**Silent.** `run()` warns only on the first failure (the `failing` flag, :256-260). When `LGTV_HOST` fails name resolution, bscpylgtv never reaches a socket attempt, so it prints nothing either. Result on 2026-07-26: ~1h of zero output while the lux hook was entirely down — indistinguishable from healthy-and-dark, since `poll_lux` is transition-only by design.

**Deafening.** When the name does resolve and the TV refuses, bscpylgtv logs `Connection attempt: N` at default level — 876 lines in 24h, burying the daemon's own INFO lines.

Note `poll_lux` is spawned inside `serve()` (:222) and cancelled in its `finally` (:237-240), so no TV connection means no lux polling at all. It self-heals on reconnect (`state=None` -> `initial_state` -> applies on first poll), so this is a diagnosability bug, not a functional one.

- [ ] Periodic heartbeat while reconnecting, so a down hook is visible in the journal
- [ ] Demote the bscpylgtv logger to WARNING
- [ ] Assert the heartbeat in tests with a fake clock

Related: [[lg-tv-enhancer-g5bm]] removes the DNS trigger but not the blind spot.
