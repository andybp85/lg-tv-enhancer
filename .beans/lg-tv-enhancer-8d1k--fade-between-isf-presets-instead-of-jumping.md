---
# lg-tv-enhancer-8d1k
title: Fade between ISF presets instead of jumping
status: draft
type: feature
priority: normal
created_at: 2026-07-30T09:54:25Z
updated_at: 2026-07-30T09:54:25Z
---

Band changes currently land as a hard cut: one `pictureMode` write and the backlight steps 90 -> 10. A ramp over a second or two would be far less jarring, especially at night.

Draft rather than todo because the obvious implementation conflicts with the design this daemon rests on. Resolve the questions below before picking it up.

## Blocker: ramping sliders may overwrite the preset's calibration

The C9 stores picture settings per (preset, input), which is exactly why `preset.py` can identify presets by their `contrast,backlight,brightness` fingerprint. If adjusting a slider while a mode is active mutates that mode's stored values, then ramping backlight through intermediate values **rewrites what ISF Bright is on that input** — corrupting the user's calibration and desynchronizing the configured `LGTV_PRESET_BRIGHT` / `LGTV_PRESET_DARK` fingerprints. An interrupted ramp (daemon crash, failed write, TV sleeping mid-fade) would leave the preset permanently stranded at an intermediate value.

**Verify this first**, before any implementation: read a preset's fingerprint, write a different backlight, read back, switch inputs away and back, and see whether the change persisted. If it does persist, a slider-ramp approach is off the table without a restore-on-failure story, and the honest answer may be that this feature isn't worth its risk.

## Second problem: intermediate states are UNKNOWN

`classify` matches full triples exactly, and anything unmatched is UNKNOWN — the guarantee that keeps Dolby Vision safe. Every intermediate frame of a fade would therefore classify as UNKNOWN, which means:

- `set_desired` returns None while UNKNOWN (hands-off), so the lux hook goes inert mid-fade
- each intermediate write emits a picture event that does not match the expected band, spending the echo expectation from [[lg-tv-enhancer-9x3h]] and potentially being misread

So a fade cannot be a loop of blind writes. It needs to be a first-class state the keeper knows about — suspending classification and correction until the ramp lands exactly on the target fingerprint. That is the [[lg-tv-enhancer-9x3h]] origin-awareness idea extended from a single echo to a sequence.

## Open questions

- [ ] Does writing a slider mutate the active preset's stored values? (decides feasibility)
- [ ] Does webOS offer any built-in transition, making all of the above moot?
- [ ] Will the TV accept ~10 writes over 2s without visible stepping or rate-limiting?
- [ ] Is backlight alone enough perceptually? It dominates the 90/10 difference, and contrast/brightness could stay a hard cut inside it
- [ ] What restores state if a fade is interrupted?
