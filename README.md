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
├── main.py   # reconcile loop + env config
├── sun.py    # pure day/night phase computation (astral)
└── tv.py     # eyeComfortMode get/set via bscpylgtv, timeout-guarded
```

## Configuration

Env-only (12-factor). Required: `LGTV_HOST`, `LGTV_LAT`, `LGTV_LON`.

| Var | Default | Meaning |
|---|---|---|
| `LGTV_HOST` | *(required)* | LG TV's LAN IP |
| `LGTV_KEY` | *(unset → interactive pairing)* | pinned webOS pairing key |
| `LGTV_LAT` / `LGTV_LON` | *(required)* | location for sunset/sunrise |
| `LGTV_POLL_SECS` | `60` | retry cadence while unreachable/pending |
| `LOG_LEVEL` | `INFO` | stdout log level (journald) |

**Pin the pairing key.** `bscpylgtv` saves its key after pairing but never
reads it back, so an unset `LGTV_KEY` makes the TV show the pairing prompt on
every restart. Reuse tv-dsp's key (`grep TVDSP_TV_KEY /etc/default/tv-dsp`) or
read a fresh one from `sqlite3 ~/.aiopylgtv.sqlite 'select value from unnamed'`.

## Deploy (Pi)

```bash
rsync -av --exclude venv --exclude .git ./ $PI_USER@$PI_HOST:/home/pi/lg-tv-enhancer/
ssh $PI_USER@$PI_HOST
cd ~/lg-tv-enhancer
python3 -m venv venv && venv/bin/pip install -r requirements.txt
sudo cp systemd/lg-tv-enhancer.env.example /etc/default/lg-tv-enhancer
sudo chmod 600 /etc/default/lg-tv-enhancer
sudoedit /etc/default/lg-tv-enhancer      # set host, key, lat/lon
sudo cp systemd/lg-tv-enhancer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lg-tv-enhancer
journalctl -u lg-tv-enhancer -f
```

## Development

Tests run anywhere — the webOS client is injected/faked, `astral` is pure math:

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt pytest
venv/bin/pytest
```

## Security model

Same trust story as tv-dsp: LAN-only, the sole credential is the webOS pairing
key, kept in root-owned `/etc/default/lg-tv-enhancer` and never committed.
