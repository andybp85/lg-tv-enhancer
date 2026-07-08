---
# lg-tv-enhancer-u55p
title: Sunset-to-sunrise Eye Comfort Mode daemon
status: completed
type: feature
priority: normal
created_at: 2026-07-08T02:38:30Z
updated_at: 2026-07-08T02:41:35Z
---

App that runs on the Pi (alongside tv-dsp) and automatically engages the LG C9's Eye Comfort Mode from sunset to sunrise.

Approach: Python daemon. Computes sunset/sunrise locally (astral) for configured lat/lon, then reconciles the TV's picture.eyeComfortMode ("on" at night, "off" by day) over the webOS LAN API (bscpylgtv, same client tv-dsp uses). Applies once per phase with read-back verification, retries while the TV is unreachable, and respects manual override for the remainder of a phase. systemd unit deploys like tv-dsp (/home/pi/<app>, venv, EnvironmentFile at /etc/default).

Key facts verified:
- bscpylgtv docs/available_settings_C9.md lists eyeComfortMode under the "picture" category (set_settings / luna path).
- Pairing key must be pinned via env (bscpylgtv never reads its own key store back; see tv-dsp-qs2m).
- Timeouts around every webOS await (dead-connection hazard; see tv-dsp 0iqm).

## Todo
- [x] sun.py: pure phase computation (day/night + next transition, polar fallback)
- [x] tv.py: apply eyeComfortMode with read-back verify, timeouts
- [x] main.py: reconcile loop, env config, logging
- [x] tests (phase logic + reconcile loop with fakes)
- [x] systemd unit + env example
- [x] README + .gitignore/.claudeignore

## Summary of Changes
- `src/sun.py` — pure day/night phase computation via astral (yesterday/today/tomorrow transition scan; polar fallback classifies by solar elevation and re-checks in 6h).
- `src/tv.py` — `apply_eye_comfort`: ephemeral webOS connection, skip-if-matching, luna `set_settings("picture", {"eyeComfortMode": ...})`, read-back verify; every await timeout-guarded. API verified against bscpylgtv 0.5.2 (the version tv-dsp pins).
- `src/main.py` — reconcile loop: applies once per phase (phase identity = next-transition time), retries while TV unreachable with once-per-outage log rate-limiting, respects manual override mid-phase; env-only config (LGTV_HOST/KEY/LAT/LON/POLL_SECS).
- `tests/` — 18 tests, all green: sun phase invariants (incl. Svalbard polar cases), TV client behavior via fake, reconcile loop via virtual clock (once-per-phase, retry, sunset crossing).
- `systemd/` — service unit (tv-dsp deploy pattern: /home/pi/<app>, venv, root-owned EnvironmentFile) + env template.
- README with deploy steps; .gitignore/.claudeignore.
