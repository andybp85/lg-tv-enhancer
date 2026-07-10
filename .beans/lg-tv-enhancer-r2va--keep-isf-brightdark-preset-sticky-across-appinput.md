---
# lg-tv-enhancer-r2va
title: Keep ISF Bright/Dark preset sticky across app/input switches
status: in-progress
type: feature
priority: normal
created_at: 2026-07-10T10:21:06Z
updated_at: 2026-07-10T12:46:16Z
---

The C9 remembers the last picture mode per app/input. User uses ISF Expert Bright/Dark presets globally (chosen by room light), not per-app. On app/input switch the TV clobbers the mode to that app's remembered ISF variant. Desired: if we were on an ISF preset before the switch and the TV switches it to the *other* ISF variant, switch it back to what we were on. If the pre-switch mode was Dolby Vision (or the new content forces DV), leave the TV's choice alone.

## Probe findings (live C9)

- `pictureMode` is **not readable** (getSystemSettings whitelist refuses it) and **not subscribable by name** — same refusal as `eyeComfortMode`.
- `pictureMode` **is writable** (blind, trusted) via `set_settings('picture', {'pictureMode': ...})`. Both `expert1`/`expert2` writes accepted and visibly changed the picture.
- `subscribe_current_app(cb)` works — pushes appId on app/input change (`youtube.leanback.v4`, `com.webos.app.hdmi1`, `netflix`).
- `subscribe_picture_settings(cb)` works — pushes `{contrast,backlight,brightness,color}` on every mode change (default keys; can't request pictureMode). Delivers current value immediately on subscribe (good for seeding). Values arrive mixed int/str — normalize.
- Ordering observed: APP EVENT precedes the follow-up PIC EVENT.

Preset fingerprints (contrast, backlight, brightness, color):
- expert1 = ISF Expert **Bright** Room -> (90, 90, 65, 50)
- expert2 = ISF Expert **Dark** Room  -> (85, 10, 50, 50)

Design consequence: identify presets by slider **fingerprint**, not name. `unknown fingerprint = hands off` covers Dolby Vision / Cinema / customized presets safely.

## DV fingerprint (live check)

Sampled Dolby Vision (Disney+): (contrast 90, backlight 90, brightness **60**, color 50).
Differs from Bright (90,90,65) **only in brightness**. Validates two decisions:
- Exact full-triple match required — a backlight-only/contrast+backlight match would misread DV as Bright and fight Dolby Vision.
- Brightness is load-bearing (sole DV-vs-Bright separator).
DV -> unknown -> hands off, as designed. One DV mode sampled; --listen + unknown-logging catch any other.
