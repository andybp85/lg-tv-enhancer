---
# lg-tv-enhancer-g5bm
title: Address the TV by its reserved IP, not a DHCP-tracking hostname
status: completed
type: task
priority: high
created_at: 2026-07-26T04:34:34Z
updated_at: 2026-07-26T04:38:07Z
---

`LGTV_HOST=LGwebOSTV.home` stops resolving whenever the TV is off long enough for its DHCP lease and DNS registration to age out. Observed 2026-07-26 00:28: `ping LGwebOSTV.home` -> `Name or service not known` on tv-dsp.home, daemon holding no TCP sockets and spinning its 5s reconnect loop.

The TV has a DHCP reservation, so its IP is stable and does not drift. Reserved IP beats a name that disappears with the lease.

Reverses the guidance added in 7eff63f ("docs: prefer a DHCP-tracking hostname for LGTV_HOST").

- [x] Point `systemd/lg-tv-enhancer.env.example` at the reserved IP, explain the reservation
- [x] Update the `LGTV_HOST` row in README env table
- [x] Update live `/etc/default/lg-tv-enhancer` on tv-dsp.home
- [x] Restart both units, confirm the keeper connects and the lux hook re-arms

## Summary of Changes

Switched `LGTV_HOST` from `LGwebOSTV.home` to the reserved IP in `systemd/lg-tv-enhancer.env.example`, the README env table, and live `/etc/default/lg-tv-enhancer` on tv-dsp.home (backup at `/etc/default/lg-tv-enhancer.bak-20260726`). Both units restarted.

The outage was worse than assumed: at 00:28 the TV was fully reachable at the reserved IP (ping 0.5ms, port 3000 open) while `LGwebOSTV.home` returned `Name or service not known`. So DNS alone had the lux hook down for ~1h with a perfectly healthy TV — the reserved IP is a fix, not just hardening.

After the switch the keeper connected in 0.8s and the lux hook armed immediately. The restart also surfaced a pre-existing startup race, filed as [[lg-tv-enhancer-mtin]].
