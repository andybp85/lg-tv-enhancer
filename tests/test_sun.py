from datetime import datetime, timedelta, timezone

from astral import Observer

from sun import DAY, NIGHT, POLAR_RECHECK, Phase, current_phase, night_factor

NYC = Observer(latitude=40.7128, longitude=-74.0060)
SVALBARD = Observer(latitude=78.2232, longitude=15.6267)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_noon_is_day():
    # 17:00 UTC == noon EST, January
    phase = current_phase(utc(2026, 1, 15, 17, 0), NYC)
    assert phase.kind == DAY


def test_midnight_is_night():
    # 05:00 UTC == midnight EST
    phase = current_phase(utc(2026, 1, 15, 5, 0), NYC)
    assert phase.kind == NIGHT


def test_until_is_in_future():
    now = utc(2026, 7, 7, 12, 0)
    phase = current_phase(now, NYC)
    assert phase.until > now


def test_phase_flips_at_transition():
    now = utc(2026, 7, 7, 12, 0)
    phase = current_phase(now, NYC)
    after = current_phase(phase.until + timedelta(seconds=1), NYC)
    assert after.kind != phase.kind
    assert after.until > phase.until


def test_consecutive_ticks_share_phase_identity():
    now = utc(2026, 7, 7, 3, 0)
    a = current_phase(now, NYC)
    b = current_phase(now + timedelta(minutes=10), NYC)
    assert (a.kind, a.until) == (b.kind, b.until)


def test_polar_summer_is_day_with_recheck():
    now = utc(2026, 6, 21, 12, 0)
    phase = current_phase(now, SVALBARD)
    assert phase.kind == DAY
    assert phase.until == now + POLAR_RECHECK


def test_polar_winter_is_night_with_recheck():
    now = utc(2026, 1, 5, 12, 0)
    phase = current_phase(now, SVALBARD)
    assert phase.kind == NIGHT
    assert phase.until == now + POLAR_RECHECK


def test_phase_brackets_now():
    now = utc(2026, 7, 7, 12, 0)
    phase = current_phase(now, NYC)
    assert phase.since <= now < phase.until


def test_phase_is_hashable_value_object():
    a = Phase(DAY, utc(2026, 1, 1), utc(2026, 1, 2))
    assert a == Phase(DAY, utc(2026, 1, 1), utc(2026, 1, 2))


RAMP = timedelta(minutes=40)


def _phase(kind, since):
    return Phase(kind, since, since + timedelta(hours=10))


def test_factor_flat_day_and_night():
    since = utc(2026, 7, 7, 0, 0)
    late = since + timedelta(hours=5)  # far past the ramp window
    assert night_factor(late, _phase(DAY, since), RAMP) == 0.0
    assert night_factor(late, _phase(NIGHT, since), RAMP) == 1.0


def test_factor_ramps_after_sunset_and_sunrise():
    since = utc(2026, 7, 7, 0, 0)
    halfway = since + RAMP / 2
    assert night_factor(halfway, _phase(NIGHT, since), RAMP) == 0.5
    assert night_factor(halfway, _phase(DAY, since), RAMP) == 0.5
    assert night_factor(since, _phase(NIGHT, since), RAMP) == 0.0
    assert night_factor(since + RAMP, _phase(NIGHT, since), RAMP) == 1.0


def test_factor_zero_ramp_is_binary():
    since = utc(2026, 7, 7, 0, 0)
    assert night_factor(since, _phase(NIGHT, since), timedelta(0)) == 1.0
    assert night_factor(since, _phase(DAY, since), timedelta(0)) == 0.0
