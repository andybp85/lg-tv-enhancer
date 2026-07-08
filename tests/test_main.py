import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from main import Config, load_config, run

CFG = Config(host="10.0.0.2", key="k", lat=40.7128, lon=-74.0060, poll_secs=60)


class StopLoop(Exception):
    pass


def drive(apply, *, start, ticks):
    """Run the reconcile loop `ticks` times with a virtual clock that advances
    by each requested sleep. Returns the (time, desired) log of apply calls."""
    now = start
    remaining = ticks

    def clock():
        return now

    async def sleep(secs):
        nonlocal now, remaining
        now += timedelta(seconds=secs)
        remaining -= 1
        if remaining <= 0:
            raise StopLoop

    calls = []

    async def wrapped(host, key, desired):
        return calls.append((clock(), desired)) or await apply(desired)

    with pytest.raises(StopLoop):
        asyncio.run(run(CFG, apply=wrapped, clock=clock, sleep=sleep))
    return calls


NOON = datetime(2026, 1, 15, 17, 0, tzinfo=timezone.utc)  # noon EST


def test_applies_once_per_phase():
    async def apply(desired):
        return True
    calls = drive(apply, start=NOON, ticks=5)
    assert [d for _, d in calls] == ["off"]  # day phase, applied exactly once


def test_retries_while_tv_unreachable_then_stops():
    outcomes = iter([False, False, True])

    async def apply(desired):
        try:
            return next(outcomes)
        except StopIteration:
            raise AssertionError("applied after success")
    calls = drive(apply, start=NOON, ticks=6)
    assert [d for _, d in calls] == ["off", "off", "off"]


def test_exception_is_retried():
    attempts = []

    async def apply(desired):
        attempts.append(desired)
        if len(attempts) < 3:
            raise ConnectionRefusedError("TV off")
        return True
    calls = drive(apply, start=NOON, ticks=6)
    assert len(calls) == 3


def test_reapplies_after_sunset():
    async def apply(desired):
        return True
    # Enough one-minute ticks to cross the ~4:56pm EST January sunset.
    calls = drive(apply, start=NOON, ticks=6 * 60)
    desireds = [d for _, d in calls]
    assert desireds[:2] == ["off", "on"]  # day applied once, then night once
    at_sunset = calls[1][0]
    assert at_sunset.hour >= 21  # ~22:00 UTC == ~5pm EST


def test_load_config_requires_host_and_coords():
    with pytest.raises(SystemExit):
        load_config(env={"LGTV_HOST": "10.0.0.2"})


def test_load_config_defaults():
    cfg = load_config(env={"LGTV_HOST": "tv", "LGTV_LAT": "40.7",
                           "LGTV_LON": "-74.0"})
    assert cfg.key is None
    assert cfg.poll_secs == 60.0
