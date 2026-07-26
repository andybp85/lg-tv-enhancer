---
# lg-tv-enhancer-mtin
title: 'Startup race: keeper reverts the lux hook''s first apply, leaving the wrong preset latched for the whole band'
status: todo
type: bug
priority: high
created_at: 2026-07-26T04:37:56Z
updated_at: 2026-07-26T04:37:56Z
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

- [ ] Reproduce under test with an injected clock
- [ ] Fix root cause
- [ ] Verify on the Pi with a dark-room restart
