# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

What the version promises — and what it doesn't — is defined by the public surface listed under
"Versioning" in the [README](README.md). The Python modules under `src/` are internal; nothing
imports this as a library, so they can change freely.

## [Unreleased]

## [0.1.0] - 2026-07-31

First versioned release. The project already worked before this point; this establishes a
baseline so future changes have something to be relative to. For history predating it, read
the git log.

### Added

- Eye Comfort scheduler (`lg-tv-enhancer.service`) — turns the mode on at sunset and off at
  sunrise, computed locally from coordinates rather than a fixed clock time.
- ISF preset keeper (`lg-tv-preset.service`) — holds Bright/Dark across app and input switches,
  and recognizes its own writes so it doesn't fight itself. Dolby Vision and unrecognized
  presets are left alone.
- Ambient-light hook — drives the ISF preset from room brightness via a BH1750 over I2C, or
  from a file for a Home Assistant/MQTT bridge or testing. Band edges form a deadband with a
  debounce hold, so the preset does not hunt.
- `tools/log_lux.py` — logs sensor readings to CSV for calibrating those band edges, with a
  one-shot mode for a single reading.
- Both daemons log their version in the startup line. Deploys are a file copy onto a box with
  no git checkout, so this is the only way to tell which build is actually running.
