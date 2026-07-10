# lg-tv-enhancer

Raspberry Pi daemon that engages the LG C9's **Eye Comfort Mode** from sunset
to sunrise, automatically. Companion to [tv-dsp](../tv-dsp/) — same TV, same
Pi, same webOS LAN client (`bscpylgtv`).

## How it works

A reconcile loop, not a scheduler:

1. Every tick (default 60 s) it computes the current solar phase for your
   coordinates ([astral](https://astral.readthedocs.io/)): **night** runs from
   sunset to the next sunrise.
2. Desired TV state follows the phase: night → `eyeComfortMode: on`,
   day → `off`. The setting lives in webOS's `"picture"` category
   (verified against bscpylgtv's `available_settings_C9.md`).
3. The change is applied **once per phase**, with read-back verification, over
   an ephemeral webOS connection. Every await is timeout-guarded — this TV can
   drop off the network without closing TCP (lesson inherited from tv-dsp).

That shape buys the behaviors that matter:

- **TV off at sunset** → the write lands on the first tick after the TV is
  back on the network. No missed nights.
- **Manual override respected** → turn the mode off by hand at night and it
  stays off until the next transition; the daemon never re-asserts mid-phase.
- **No spam** → once a phase is applied, the TV isn't touched again until the
  next sunrise/sunset.

```
src/
├── main.py          # eye-comfort reconcile loop + env config
├── sun.py           # pure day/night phase computation (astral)
├── tv.py            # eyeComfortMode get/set via bscpylgtv, timeout-guarded
├── preset.py        # pure ISF preset classification + Keeper state machine
└── preset_daemon.py # ISF preset keeper: subscribe to app + picture, correct
```

## ISF preset keeper (second daemon)

The C9 remembers the last picture mode **per app/input**, but ISF Bright/Dark is
really a *global* choice (room light), not a per-app one. `preset_daemon.py`
holds a persistent webOS connection and, when an app/input switch flips you to
the other ISF variant, writes `pictureMode` back to the one you were on.

- `pictureMode` is **unreadable** on this firmware (same whitelist refusal as
  `eyeComfortMode`), so presets are recognized by their picture-settings
  **fingerprint** `(contrast, backlight, brightness)`, pushed over
  `subscribe_picture_settings`. Corrections are blind `pictureMode` writes.
- **Unknown fingerprint → hands off.** Dolby Vision, Cinema, Game, and any
  customized preset are left alone — no enumeration needed. (Sampled DV
  `(90,90,60)` sits one brightness point from Bright `(90,90,65)`, which is why
  matching uses the full triple.)
- **Manual Bright↔Dark** (no app switch) is respected and becomes the new
  sticky value.

Calibrate or re-derive fingerprints (prints each mode's tuple as you flip):

```bash
venv/bin/python src/preset_daemon.py --listen
```

Config lives in the same env file as the eye-comfort daemon; see the table below.

## Configuration

Env-only (12-factor). Required: `LGTV_HOST`, `LGTV_LAT`, `LGTV_LON`.

| Var | Default | Meaning |
|---|---|---|
| `LGTV_HOST` | *(required)* | LG TV's LAN IP |
| `LGTV_KEY` | *(unset → interactive pairing)* | pinned webOS pairing key |
| `LGTV_LAT` / `LGTV_LON` | *(required)* | location for sunset/sunrise |
| `LGTV_POLL_SECS` | `60` | retry cadence while unreachable/pending |
| `LOG_LEVEL` | `INFO` | stdout log level (journald) |
| `LGTV_PRESET_BRIGHT` / `LGTV_PRESET_DARK` | `90,90,65` / `85,10,50` | ISF preset fingerprints `contrast,backlight,brightness` |
| `LGTV_MODE_BRIGHT` / `LGTV_MODE_DARK` | `expert1` / `expert2` | pictureMode written to restore each preset |
| `LGTV_SETTLE_SECS` | `3` | app-change → mode-settle window |

**Pin the pairing key.** `bscpylgtv` saves its key after pairing but never
reads it back, so an unset `LGTV_KEY` makes the TV show the pairing prompt on
every restart. Reuse tv-dsp's key (`grep TVDSP_TV_KEY /etc/default/tv-dsp`) or
read a fresh one from `sqlite3 ~/.aiopylgtv.sqlite 'select value from unnamed'`.

## Deploy (Pi)

Copy `.env.example` to `.env` (git-ignored) and set your Pi user/host, then:

```bash
set -a; source .env; set +a
rsync -av --delete --exclude venv --exclude .git --exclude __pycache__ --exclude .pytest_cache \
    ./ "$PI_USER@$PI_HOST:/home/$PI_USER/lg-tv-enhancer/"
ssh "$PI_USER@$PI_HOST"
cd ~/lg-tv-enhancer
python3 -m venv venv && venv/bin/pip install -r requirements.txt
sudo cp systemd/lg-tv-enhancer.env.example /etc/default/lg-tv-enhancer
sudo chmod 600 /etc/default/lg-tv-enhancer
sudoedit /etc/default/lg-tv-enhancer      # set host, key, lat/lon
# edit User/paths in the unit if your Pi account isn't `pi`
sudo cp systemd/lg-tv-enhancer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lg-tv-enhancer
journalctl -u lg-tv-enhancer -f
```

The preset keeper is a second unit installed the same way:

```bash
sudo cp systemd/lg-tv-preset.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lg-tv-preset
journalctl -u lg-tv-preset -f
```

## Development

Tests run anywhere — the webOS client is injected/faked, `astral` is pure math:

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt pytest
venv/bin/pytest
```

## Reference: the bigger TV-enhancement projects

Ideas beyond this daemon's scope, kept here as jumping-off points:

- **Internal LUT calibration** — the C9 accepts 3D LUT uploads into its
  calibration slots; [bscpylgtv](https://github.com/chros73/bscpylgtv) was
  built for this (`cal_commands`/`lut_tools`), driven by
  [DisplayCAL](https://displaycal.net/) or
  [HCFR](https://sourceforge.net/projects/hcfr/) plus a colorimeter. Guides:
  [profiling SDR](https://github.com/chros73/bscpylgtv/tree/master/docs/guides/profiling_sdr),
  [calibrating HDR10](https://github.com/chros73/bscpylgtv/tree/master/docs/guides/calibrating_hdr10),
  [setting presets](https://github.com/chros73/bscpylgtv/tree/master/docs/guides/setting_presets),
  [mitigating DoVi raised black](https://github.com/chros73/bscpylgtv/tree/master/docs/guides/mitigating_dovi_raised_black).
- **DIY Ambilight** —
  [Hyperion](https://github.com/hyperion-project/hyperion.ng) or
  [WLED](https://kno.wled.ge/) driving LEDs behind the panel from an HDMI
  grabber. Caveat on webOS: a grabber can't see the TV's own apps, only
  external sources.
- **Home Assistant** — the
  [webostv integration](https://www.home-assistant.io/integrations/webostv/)
  for presence/scene automations; same LAN API underneath, coexists with
  this daemon.
- **Power/idle automation** — wake-on-LAN, HDMI-CEC from the Pi
  (`cec-utils`) for when webOS's network stack is asleep.

## Security model

Same trust story as tv-dsp: LAN-only, the sole credential is the webOS pairing
key, kept in root-owned `/etc/default/lg-tv-enhancer` and never committed.
