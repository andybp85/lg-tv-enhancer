# Design: keep ISF Bright/Dark preset sticky across app/input switches

Bean: `lg-tv-enhancer-r2va`. Date: 2026-07-10.

## Problem

The C9 remembers the last picture mode **per app/input**. The user picks between two
ISF Expert presets — **Bright Room** (`expert1`) and **Dark Room** (`expert2`) — by
room light, as a *global* choice, not per app. So on every app/input switch the TV
"helpfully" restores that app's remembered ISF variant, which is usually the wrong one.

Desired behavior (confirmed with user):

- Track the picture mode active **just before** an app/input switch.
- After the switch settles, if the TV flipped to the **other ISF variant**, write back
  the one you were on.
- If the pre-switch mode was **Dolby Vision** (or the new content forces DV), leave the
  TV's choice alone — its DV behavior is correct.
- A **manual** Bright↔Dark change (no app switch) is respected: it silently becomes the
  new sticky value.

## Feasibility (verified on the live C9)

Probes run against the TV via `bscpylgtv` on the Pi. Findings:

- `pictureMode` is **not readable** — `getSystemSettings` whitelists readable keys and
  refuses it (`"Some keys are not allowed for the request ( pictureMode )"`), the same
  refusal that makes `eyeComfortMode` write-only (bean `lg-tv-enhancer-ccuj`). It is
  **not subscribable by name** either.
- `pictureMode` **is writable** — blind, trusted, via
  `set_settings("picture", {"pictureMode": "expert1"})`. Writes were accepted and
  visibly changed the picture.
- `subscribe_current_app(cb)` works — pushes the foreground appId on every app/input
  change (`youtube.leanback.v4`, `com.webos.app.hdmi1`, `netflix` — external inputs
  included).
- `subscribe_picture_settings(cb)` works with the **default keys**
  `{contrast, backlight, brightness, color}`, pushing an event on every mode change.
  It cannot request `pictureMode`. It delivers the current value **immediately on
  subscribe** (useful for seeding). Values arrive mixed `int`/`str` — normalize.
- Observed ordering: the app event precedes the follow-up picture event.

### Preset fingerprints

Because `pictureMode` is invisible by name, presets are identified by their slider
**fingerprint** `(contrast, backlight, brightness)` (`color` was always `50`, ignored):

| pictureMode | on-screen | contrast | backlight | brightness |
|---|---|---|---|---|
| `expert1` | ISF Expert Bright Room | 90 | 90 | 65 |
| `expert2` | ISF Expert Dark Room | 85 | 10 | 50 |

The `backlight 90` vs `10` gap is a strong separator. **Any fingerprint that matches
neither is `unknown`** — and `unknown = hands off`. This is what makes Dolby Vision,
Cinema, Game, and any customized preset safe *without* enumerating them.

## Strategy

Persistent connection, two subscriptions feeding one pure reducer. Identify presets by
fingerprint (read-only); act by blind-writing `pictureMode` only.

**We never write `contrast`/`backlight`/`brightness`.** Those tuples are recognition
values only; the TV owns each preset's calibrated sliders. Worst case on a fingerprint
mismatch is failing *safe* (`unknown` → do nothing), never disturbing calibration.

## State machine

State: `current_preset ∈ {bright, dark, unknown}`, plus an optional armed settle window
`(preset_before, deadline)`.

- **Picture event** → `classify(fingerprint)` → update `current_preset`. If a window is
  armed and this event is within its deadline, evaluate a correction (below) and disarm.
- **App event** → snapshot `preset_before = current_preset`; arm a window with
  `deadline = now + LGTV_SETTLE_SECS`.
- **Correction rule** (on the first picture event inside the window): if `preset_before`
  and `preset_after` are the **two different ISF variants** (`{bright, dark}` and not
  equal), write back `preset_before`. Otherwise do nothing. Disarm either way.
- **Picture event outside any window** = manual change → only updates `current_preset`
  (the new sticky value).

Properties (all match confirmed intent):

- Bright/Dark stays sticky across app/input hops.
- Manual Bright↔Dark (no app event) becomes the new sticky value; never corrected.
- DV in either direction yields `unknown` on one side → correction rule is false → no
  action. "Coming from DV, ignore."
- The corrective write's own picture event resolves `current_preset` back to
  `preset_before`; with the window disarmed it cannot loop.
- Ordering edge: if a picture event ever beats its app event, that one correction is
  missed and treated as manual. Acceptable degradation.

## Modules

Separate service from the eye-comfort daemon (different cadence and connection
lifecycle). `main.py`, `tv.py`, `sun.py` are untouched.

- `src/preset.py` — **pure**. `Preset` consts (`BRIGHT`/`DARK`/`UNKNOWN`),
  `classify(settings, *, bright, dark) -> Preset`, and a `Keeper` reducer with
  `on_app_change(now)` and `on_picture_change(settings, now) -> Correction | None`.
  Clock injected. No TV, no I/O — fully unit-testable.
- `src/preset_daemon.py` — **I/O + entry point**. Connect, subscribe to both feeds,
  translate callbacks into reducer calls, perform blind `pictureMode` writes, reconnect
  with backoff, env config. Every await timeout-guarded (tv-dsp dead-connection lesson).
  A `--listen` mode prints fingerprints as modes are flipped (calibration / collision
  check), no writes.
- `systemd/lg-tv-preset.service` + additions to the env example.

A shared client factory extracted from `tv.py` was considered and rejected: the
connection models differ (ephemeral connect-reconcile-disconnect vs. long-lived
subscription), so sharing would couple more than it saves.

## Configuration

Env-only (12-factor). Reuses `LGTV_HOST` / `LGTV_KEY`.

| Var | Default | Meaning |
|---|---|---|
| `LGTV_PRESET_BRIGHT` | `90,90,65` | Bright fingerprint `contrast,backlight,brightness` |
| `LGTV_PRESET_DARK` | `85,10,50` | Dark fingerprint |
| `LGTV_MODE_BRIGHT` | `expert1` | pictureMode value written for Bright |
| `LGTV_MODE_DARK` | `expert2` | pictureMode value written for Dark |
| `LGTV_SETTLE_SECS` | `3` | app-change → mode-settle window (seconds) |

Fingerprints are matched **exactly** after int-normalization; `color` is ignored. Exact
match keeps the "unknown = hands off" guarantee tight (a DV mode won't be mistaken for
ISF). Every `unknown` fingerprint observed is logged so real-world DV/Cinema values land
in journald for review and easy config updates via `--listen`.

## Robustness

- Persistent client with ping enabled; on any drop, reconnect with backoff.
- On (re)connect, the picture subscription's immediate push **seeds `current_preset`** —
  no blind first move after a reconnect.
- All awaits timeout-guarded; a dead connection fails the attempt and triggers reconnect.

## Testing

- `preset.py` (pure) — synthetic event sequences + injected clock:
  - correction fires both directions (bright→dark restores bright; dark→bright restores
    dark);
  - same-preset app change → no correction;
  - manual change (picture event, no preceding app event) → no correction, updates
    sticky;
  - DV in and out (`unknown` on one side) → no correction;
  - picture event after window expiry → treated as manual;
  - corrective write does not loop;
  - string-typed slider values classify correctly.
- `preset_daemon.py` — light, with a fake client (mirrors how `main.py` injects `apply`).

## Open item (non-blocking)

Verify no DV/Cinema fingerprint collides with `(90,90,65)` or `(85,10,50)`. The
`--listen` mode covers this: flip through modes incl. a real DV title, confirm distinct
fingerprints. Until then, exact-match + unknown-logging keeps behavior safe.

## Possible interaction to watch

Writing `pictureMode` might reset the preset's stored `eyeComfortMode`, which the
eye-comfort daemon only asserts once per solar phase. If observed in practice, revisit
whether the preset write should also re-assert the desired eye-comfort state. Not
addressed now (unverified, likely independent settings).
