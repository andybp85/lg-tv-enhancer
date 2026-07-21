from datetime import datetime, timedelta, timezone

from lux import BRIGHT, DARK, Bands, BandState, initial_state, select_band

# Deadband straddling the room's evening-dim dwell (see README measurement notes):
# flip to Dark only once light is genuinely gone, flip to Bright once it returns.
BANDS = Bands(enter_dark_below=1.0, enter_bright_above=3.0, hold_secs=30.0)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def hold(state, lux, start, bands=BANDS, *, secs):
    """Feed the same lux for `secs`, one reading per second, from `start`."""
    now = start
    end = start + timedelta(seconds=secs)
    while now <= end:
        state = select_band(state, lux, now, bands)
        now += timedelta(seconds=1)
    return state


def test_cold_start_snaps_without_waiting():
    # No prior band to hold, so startup applies immediately, no debounce.
    assert initial_state(0.0, BANDS).band == DARK
    assert initial_state(50.0, BANDS).band == BRIGHT


def test_cold_start_in_deadband_defaults_bright():
    # Safer to open on Bright than to strand the user in Dark at boot.
    assert initial_state(2.0, BANDS).band == BRIGHT


def test_darkness_held_long_enough_commits_dark():
    start = utc(2026, 7, 20, 3, 0)
    state = hold(initial_state(50.0, BANDS), 0.0, start, secs=60)
    assert state.band == DARK


def test_brief_darkness_does_not_flip():
    # A shadow across the sensor for 20s must not retint the room.
    start = utc(2026, 7, 20, 20, 0)
    state = hold(initial_state(50.0, BANDS), 0.0, start, secs=20)
    assert state.band == BRIGHT


def test_deadband_holds_current_band():
    # Evening dwell at 2 lux: whatever we were, we stay — that's the hysteresis.
    from_bright = select_band(initial_state(50.0, BANDS), 2.0, utc(2026, 7, 20, 19), BANDS)
    assert from_bright.band == BRIGHT
    from_dark = select_band(initial_state(0.0, BANDS), 2.0, utc(2026, 7, 20, 5), BANDS)
    assert from_dark.band == DARK


def test_must_cross_far_edge_to_flip_back():
    start = utc(2026, 7, 20, 3, 0)
    dark = hold(initial_state(50.0, BANDS), 0.0, start, secs=90)
    # 2.0 is above enter_dark_below but not above enter_bright_above: stay Dark.
    still_dark = hold(dark, 2.0, start + timedelta(minutes=5), secs=90)
    assert still_dark.band == DARK
    # Cross the far edge and hold: now it flips.
    bright = hold(still_dark, 5.0, start + timedelta(minutes=10), secs=90)
    assert bright.band == BRIGHT


def test_interrupted_debounce_restarts_timer():
    start = utc(2026, 7, 20, 20, 0)
    state = hold(initial_state(50.0, BANDS), 0.0, start, secs=20)  # 20s < 30s hold
    assert state.band == BRIGHT
    # A blink of light cancels the in-flight flip...
    state = select_band(state, 50.0, start + timedelta(seconds=21), BANDS)
    assert state.pending is None
    # ...so the next dark spell must serve its own full 30s, not inherit credit.
    state = hold(state, 0.0, start + timedelta(seconds=22), secs=20)
    assert state.band == BRIGHT


def test_committing_clears_pending():
    start = utc(2026, 7, 20, 3, 0)
    state = hold(initial_state(50.0, BANDS), 0.0, start, secs=60)
    assert state.band == DARK
    assert state.pending is None and state.since is None


def test_settling_back_clears_pending():
    # Start a flip toward Dark, then light returns before the hold elapses.
    start = utc(2026, 7, 20, 20, 0)
    pending = select_band(initial_state(50.0, BANDS), 0.0, start, BANDS)
    assert pending.pending == DARK
    settled = select_band(pending, 50.0, start + timedelta(seconds=10), BANDS)
    assert settled.band == BRIGHT
    assert settled.pending is None


def test_band_state_is_hashable_value_object():
    assert BandState(DARK, None, None) == BandState(DARK, None, None)
