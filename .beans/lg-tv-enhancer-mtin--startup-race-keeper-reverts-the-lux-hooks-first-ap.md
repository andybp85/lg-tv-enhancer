---
# lg-tv-enhancer-mtin
title: 'Startup race: keeper reverts the lux hook''s first apply, leaving the wrong preset latched for the whole band'
status: completed
type: bug
priority: high
created_at: 2026-07-26T04:37:56Z
updated_at: 2026-07-30T03:28:12Z
---

Reproduced on tv-dsp.home at 2026-07-26 00:35:54 by restarting `lg-tv-preset` in a dark room (0.0 lux):

```
00:35:54.368 wrote pictureMode=expert2
00:35:54.369 ambient lux -> dark (0.0 lux)
00:35:54.409 app switch flipped away from bright; restoring
00:35:54.466 wrote pictureMode=expert1
```

Then silence. Live fingerprint read at 00:38 confirmed `contrast=90 backlight=90 brightness=65` — the **bright** preset, in a pitch-dark room.

## Cause

`serve()` subscribes `current_app` (:219) whose immediate push arms a 3s settle window. The comment at :216-218 calls this "harmless in steady state (no picture event follows, so it expires as manual)" — an assumption the lux hook invalidates. With `LGTV_LUX_SOURCE` set, `poll_lux` starts one line later (:222) and its first apply lands *inside* that window, so the keeper reads its own sibling task's write as an app-driven flip and restores the seeded preset.

## Why it latches

`poll_lux` records `applied_band = "dark"` because its write succeeded (:174-176), then goes quiet by design — apply-once-per-band. The keeper meanwhile holds desired=bright. Nothing reconciles the two until the band *changes*, so a restart in a dark room strands the TV in Bright until lux next crosses 3.0 in the morning. Overnight is the worst case: maximum backlight, entire night, no correction.

Pre-existing since 7f7w shipped; unmasked by the restart in [[lg-tv-enhancer-g5bm]], not caused by it.

## Fix directions (pick during debugging)

- Suppress the settle window for the immediate on-subscribe app push (it arms on a non-event)
- Or start `poll_lux` only after the initial settle window expires
- Or make the keeper recognize writes originating from its own process rather than treating them as external flips
- Regression test: fake clock, lux source reading dark, assert the seeded-bright keeper does not revert the first apply

- [x] Reproduce under test with an injected clock
- [x] Fix root cause
- [x] Verify on the Pi with a dark-room restart

## Summary of Changes

Root cause was `Keeper.on_app_change` treating every app event as a switch. Subscribing to the current app delivers the foreground app immediately, so `serve()` armed a settle window on a snapshot; `poll_lux`s first apply landed inside it and `_evaluate(BRIGHT, DARK)` read the daemons own write as an app-induced flip.

Fix: the keeper now takes the app id and arms only on a genuine change, with the first observation recording a baseline. A module-level `_UNSEEN` sentinel distinguishes never-observed from an app id of None, so a TV reporting a null foreground app still gets a baseline instead of re-arming forever.

Tests: three keeper-level cases (snapshot does not arm, a real switch after the snapshot still corrects, a repeated same-app event does not arm) plus a wire-level regression replaying the incident sequence. The wire-level test was confirmed to fail against the pre-fix source (it wrote expert1) before the fix went in. Eight existing tests never modeled the on-subscribe snapshot and now route through an `app_switch` helper that sends it first. 90 pass.

Verified on the Pi at 00:47 with a dark-room restart: `ambient lux -> dark (0.0 lux)` with no restoring line, TV fingerprint read back as `85,10,50` (Dark), one write in three minutes.

Verified in production 2026-07-29 23:27:21: a real switch (HDMI1 -> youtube.leanback.v4) flipped the preset and the keeper logged `app switch flipped away from bright; restoring` + `wrote pictureMode=expert1`. Fingerprint read back as 90,90,65 (Bright).

A read-only probe on the app subscription confirmed the two facts the fix depends on: the on-subscribe push (`youtube.leanback.v4`) arrives as a baseline that must not arm, and a real switch to `com.webos.app.hdmi1` is seen as a changed id that does arm. Since `_evaluate` fires only when both presets are recognized ISF variants, this also confirms HDMI1's per-input fingerprints are calibrated.
