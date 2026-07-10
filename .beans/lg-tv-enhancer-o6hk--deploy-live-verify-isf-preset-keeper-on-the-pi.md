---
# lg-tv-enhancer-o6hk
title: Deploy + live-verify ISF preset keeper on the Pi
status: completed
type: task
priority: normal
created_at: 2026-07-10T13:37:31Z
updated_at: 2026-07-10T14:45:38Z
---

Post-merge verification for lg-tv-enhancer-r2va (not yet done — code is merged to main but not deployed).

1. rsync main to the Pi; install systemd/lg-tv-preset.service; enable --now.
2. Run `src/preset_daemon.py --listen`: flip Bright > Dark > Bright and confirm printed classifications; play a Dolby Vision title and confirm it prints '-> unknown' (no collision with (90,90,65)/(85,10,50)).
3. With the daemon running: on ISF Bright, switch between two apps that remember different ISF variants; confirm it snaps back to Bright within the settle window; confirm a DV title is left alone.
4. Watch `journalctl -u lg-tv-preset -f` for 'restored pictureMode=' lines and any unexpected 'unknown' fingerprints (would reveal a mis-set config tuple or an uncatalogued DV mode).

Also watch whether writing pictureMode resets the preset's eyeComfortMode (possible interaction flagged in the design doc).

## Deploy + verify results (2026-07-10)

Deployed: rsynced main to Pi, installed `/etc/systemd/system/lg-tv-preset.service` (User=$PI_USER, matches eye-comfort unit), `enable --now`. Service **active**, log shows 'connected to <TV_IP>', subscribed, no errors. Defaults in effect (bright=expert1 dark=expert2, settle 3s).

Verified:
- Live `--listen`: current Bright classifies as `(90,90,65) -> bright` ✓ (config tuples match calibration).
- Dark `(85,10,50)` and DV `(90,90,60)` confirmed live during design; DV distinct -> unknown/hands-off.
- Write/subscribe/connect all confirmed.

**Still open — observe a real correction end-to-end:** during testing no app switch actually flipped the ISF variant, so zero corrections fired (correct: no false positives). Need to see a `restored pictureMode=` line when a genuine app switch brings up the wrong variant. Watch `journalctl -u lg-tv-preset -f` in normal use. If it doesn't snap back, bump `LGTV_SETTLE_SECS` (currently 3) or re-run `--listen` to recheck fingerprints.

Note: also still worth confirming a pictureMode write doesn't reset the preset's eyeComfortMode (design-doc interaction flag).

## Summary of Changes

Deployed and **verified end-to-end** on the live C9 (2026-07-10).

Root cause of the initial no-corrections: (1) Energy Saving was driving OLED Light, so `backlight` in the fingerprint drifted; (2) the C9 stores picture settings **per input**, so Xfinity's ISF Bright/Dark ((90,100,60)/(85,28,50)) differ from the apps' ((90,90,65)/(85,10,50)) and read as 'unknown'.

Fixes:
- Turned Energy Saving off (also correct for calibrated ISF) -> stable fingerprints.
- Implemented **multi-fingerprint per preset** (commit 13a74c4): `classify` matches a set; `LGTV_PRESET_BRIGHT/DARK` accept ';'-separated tuples. 46 tests pass.
- Pi config: `LGTV_PRESET_BRIGHT="90,90,65;90,100,60"`, `LGTV_PRESET_DARK="85,10,50;85,28,50"`.

Verified: journal shows corrections firing both directions on real app<->input switches (restored pictureMode=expert1/expert2, ~0.2s). DV (90,90,60) still distinct from all four ISF tuples -> hands off.

Note: the app-vs-input framing was a red herring — inputs use the same code path as apps; per-input *calibration* was the real issue.
