import pytest

from preset_daemon import Config, load_config


def test_load_config_requires_host():
    with pytest.raises(SystemExit):
        load_config(env={})


def test_load_config_defaults():
    cfg = load_config(env={"LGTV_HOST": "tv"})
    assert cfg.key is None
    assert cfg.bright_fps == frozenset({(90, 90, 65)})
    assert cfg.dark_fps == frozenset({(85, 10, 50)})
    assert cfg.bright_mode == "expert1"
    assert cfg.dark_mode == "expert2"
    assert cfg.settle_secs == 3.0


def test_load_config_custom_fingerprints_and_modes():
    cfg = load_config(env={
        "LGTV_HOST": "tv",
        "LGTV_KEY": "abc",
        "LGTV_PRESET_BRIGHT": "88,92,66",
        "LGTV_PRESET_DARK": "80,5,48",
        "LGTV_MODE_BRIGHT": "expert2",
        "LGTV_MODE_DARK": "expert1",
        "LGTV_SETTLE_SECS": "5",
    })
    assert cfg.key == "abc"
    assert cfg.bright_fps == frozenset({(88, 92, 66)})
    assert cfg.dark_fps == frozenset({(80, 5, 48)})
    assert cfg.bright_mode == "expert2"
    assert cfg.settle_secs == 5.0


def test_load_config_multi_fingerprint_per_preset():
    # Per-input calibration: apps + Xfinity Bright/Dark, ';'-separated.
    cfg = load_config(env={
        "LGTV_HOST": "tv",
        "LGTV_PRESET_BRIGHT": "90,90,65;90,100,60",
        "LGTV_PRESET_DARK": "85,10,50;85,28,50",
    })
    assert cfg.bright_fps == frozenset({(90, 90, 65), (90, 100, 60)})
    assert cfg.dark_fps == frozenset({(85, 10, 50), (85, 28, 50)})


import asyncio

from preset_daemon import build_keeper, wire


class FakeClient:
    """Records pictureMode writes; stands in for bscpylgtv's WebOsClient."""

    def __init__(self) -> None:
        self.set_calls: list[dict[str, object]] = []

    async def set_settings(self, category: str, settings: dict[str, object]) -> None:
        assert category == "picture"
        self.set_calls.append(settings)


CFG = Config(host="tv", key="k", bright_fps=frozenset({(90, 90, 65)}),
             dark_fps=frozenset({(85, 10, 50)}),
             bright_mode="expert1", dark_mode="expert2", settle_secs=3.0,
             lux_poll_secs=30.0, lux_dark_below=1.0, lux_bright_above=3.0,
             lux_hold_secs=30.0)


def _bright() -> dict[str, object]:
    return {"contrast": 90, "backlight": 90, "brightness": 65, "color": "50"}


def _dark() -> dict[str, object]:
    return {"contrast": 85, "backlight": 10, "brightness": 50, "color": "50"}


def _dv() -> dict[str, object]:
    return {"contrast": 90, "backlight": 90, "brightness": 60, "color": "50"}


def test_wire_writes_pictureMode_on_app_flip():
    async def scenario():
        client = FakeClient()
        keeper = build_keeper(CFG)
        t = [0.0]
        on_pic, on_app = wire(keeper, client, clock=lambda: t[0])
        await on_pic(_bright())          # seed current = bright
        t[0] = 10.0
        await on_app("home")     # on-subscribe snapshot: baseline only
        await on_app("netflix")
        t[0] = 10.5
        await on_pic(_dark())            # TV flipped to dark -> correct
        await asyncio.sleep(0)           # let the spawned write task run
        assert client.set_calls == [{"pictureMode": "expert1"}]

    asyncio.run(scenario())


def test_wire_does_not_revert_the_lux_hooks_first_apply():
    """The startup sequence that stranded the TV in Bright at 0.0 lux (mtin).

    Subscribing pushes the current picture, then the current app; the lux task
    starts and applies Dark. The echo of that write must not be corrected back
    to Bright, which requires `wire` to hand the app id to the keeper so the
    snapshot is recognized as a non-switch.
    """
    async def scenario():
        client = FakeClient()
        keeper = build_keeper(CFG)
        t = [0.0]
        on_pic, on_app = wire(keeper, client, clock=lambda: t[0])
        await on_pic(_bright())          # picture snapshot: current = bright
        await on_app("home")             # app snapshot, not a switch
        assert keeper.set_desired("dark") is not None   # lux hook applies dark
        t[0] = 0.2
        await on_pic(_dark())            # the write echoes back as an event
        await asyncio.sleep(0)
        assert client.set_calls == []    # no "restoring bright"

    asyncio.run(scenario())


def test_wire_leaves_dolby_vision_alone():
    async def scenario():
        client = FakeClient()
        keeper = build_keeper(CFG)
        t = [0.0]
        on_pic, on_app = wire(keeper, client, clock=lambda: t[0])
        await on_pic(_bright())
        t[0] = 5.0
        await on_app("home")     # on-subscribe snapshot: baseline only
        await on_app("disneyplus")
        t[0] = 5.3
        await on_pic(_dv())              # DV -> UNKNOWN -> hands off
        await asyncio.sleep(0)
        assert client.set_calls == []

    asyncio.run(scenario())


from preset_daemon import run


class StopLoop(Exception):
    pass


def test_run_reconnects_after_serve_failure():
    async def scenario():
        attempts = []

        async def flaky_serve(cfg, *, source=None, on_up=None):
            attempts.append(1)
            raise ConnectionResetError("connection dropped")

        ticks = [0]

        async def sleep(secs):
            ticks[0] += 1
            if ticks[0] >= 3:
                raise StopLoop

        with pytest.raises(StopLoop):
            await run(CFG, serve=flaky_serve, sleep=sleep)
        assert len(attempts) == 3  # serve retried each time the backoff elapsed

    asyncio.run(scenario())


import logging


def _messages(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records]


def test_run_logs_a_heartbeat_while_it_cannot_connect(caplog):
    # An unreachable TV must not be silent: poll_lux dies with the connection,
    # so without a periodic line a dead hook reads exactly like a quiet healthy
    # one (lg-tv-enhancer-ulp5).
    async def scenario():
        async def dead_serve(cfg, *, source=None, on_up=None):
            raise ConnectionRefusedError("refused")

        t = [0.0]

        async def sleep(secs):
            t[0] += secs
            if t[0] > 700:
                raise StopLoop

        with pytest.raises(StopLoop):
            await run(CFG, serve=dead_serve, sleep=sleep, clock=lambda: t[0])

    # INFO, because a refused connection means the TV is off — the normal case.
    with caplog.at_level(logging.INFO):
        asyncio.run(scenario())
    beats = [m for m in _messages(caplog) if "still unreachable" in m]
    assert len(beats) == 2  # at 300s and 600s of simulated downtime
    assert "lux hook is not polling" in beats[0]


def test_a_drop_after_a_successful_reconnect_warns_again(caplog):
    # serve() never returns normally, so the old `failing` flag latched True and
    # only the first disconnect of a process's life was ever reported.
    async def scenario():
        calls = [0]

        async def flapping_serve(cfg, *, source=None, on_up=None):
            calls[0] += 1
            if calls[0] == 2 and on_up is not None:
                on_up()  # connected this time, then dropped
            raise ConnectionResetError("dropped")

        async def sleep(secs):
            if calls[0] >= 3:
                raise StopLoop

        with pytest.raises(StopLoop):
            await run(CFG, serve=flapping_serve, sleep=sleep, clock=lambda: 0.0)

    with caplog.at_level(logging.INFO):
        asyncio.run(scenario())
    # Both drops are the same failure class, so only on_up resetting the outage
    # can produce a second opening line.
    opened = [m for m in _messages(caplog) if "TV unreachable" in m]
    assert len(opened) == 2  # the first drop, and the one after reconnecting


import errno
import socket

from preset_daemon import (
    FAILURE_AUTH,
    FAILURE_CONFIG,
    FAILURE_NORMAL,
    FAILURE_UNEXPECTED,
    _describe,
    classify_failure,
)


class PyLGTVPairException(Exception):
    """Shaped like the real one: sets .message without calling super().__init__,
    so str(exc) is empty. Named to match, since preset_daemon classifies by name
    to keep the bscpylgtv import lazy."""

    def __init__(self, message):
        self.message = message


def test_classify_a_powered_off_tv_as_normal():
    assert classify_failure(ConnectionRefusedError()) == FAILURE_NORMAL
    assert classify_failure(TimeoutError()) == FAILURE_NORMAL
    assert classify_failure(ConnectionResetError()) == FAILURE_NORMAL
    assert classify_failure(OSError(errno.EHOSTUNREACH, "no route")) == FAILURE_NORMAL


def test_classify_name_resolution_failure_as_config():
    # gaierror subclasses OSError, so it must be tested before the errno checks.
    assert classify_failure(socket.gaierror(-2, "Name or service not known")) == FAILURE_CONFIG


def test_classify_pairing_rejection_as_auth():
    assert classify_failure(PyLGTVPairException("Unable to pair")) == FAILURE_AUTH


def test_classify_a_programming_error_as_unexpected():
    # A bug must never be filed under "the TV is probably off" and logged at INFO.
    assert classify_failure(TypeError("got an unexpected keyword argument")) == FAILURE_UNEXPECTED


def test_describe_falls_back_to_a_message_attribute():
    # bscpylgtv's exceptions and asyncio.TimeoutError both leave str(exc) empty.
    assert _describe(PyLGTVPairException("Unable to pair")) == "PyLGTVPairException: Unable to pair"
    assert _describe(TimeoutError()) == "TimeoutError"
    assert _describe(ConnectionRefusedError("refused")) == "ConnectionRefusedError: refused"


def _run_until_stopped(exc: BaseException, calls_before_stop: int = 2):
    async def scenario():
        calls = [0]

        async def failing_serve(cfg, *, source=None, on_up=None):
            calls[0] += 1
            raise exc

        async def sleep(secs):
            if calls[0] >= calls_before_stop:
                raise StopLoop

        with pytest.raises(StopLoop):
            await run(CFG, serve=failing_serve, sleep=sleep, clock=lambda: 0.0)

    asyncio.run(scenario())


def test_an_off_tv_is_reported_at_info_not_as_an_error(caplog):
    # A powered-off TV is the normal overnight state and must not read as a fault.
    with caplog.at_level(logging.INFO):
        _run_until_stopped(ConnectionRefusedError("refused"))
    levels = {r.levelno for r in caplog.records}
    assert logging.INFO in levels
    assert logging.WARNING not in levels and logging.ERROR not in levels


def test_a_pairing_rejection_is_reported_as_an_error(caplog):
    # Retrying cannot fix a bad key, so this one has to be loud and actionable.
    with caplog.at_level(logging.INFO):
        _run_until_stopped(PyLGTVPairException("Unable to pair"))
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "Unable to pair" in errors[0].getMessage()


def test_a_change_of_failure_class_mid_outage_is_reported(caplog):
    # The 2026-07-26 incident went from "refused" to "cannot resolve" while the
    # TV stayed reachable by IP. That switch is the diagnosis, so it must not
    # wait out a 300s heartbeat to appear.
    async def scenario():
        calls = [0]

        async def degrading_serve(cfg, *, source=None, on_up=None):
            calls[0] += 1
            if calls[0] == 1:
                raise ConnectionRefusedError("refused")
            raise socket.gaierror(-2, "Name or service not known")

        async def sleep(secs):
            if calls[0] >= 3:
                raise StopLoop

        with pytest.raises(StopLoop):
            await run(CFG, serve=degrading_serve, sleep=sleep, clock=lambda: 0.0)

    with caplog.at_level(logging.INFO):
        asyncio.run(scenario())
    assert any("TV unreachable" in m for m in _messages(caplog))
    resolve = [r for r in caplog.records if "cannot resolve" in r.getMessage()]
    assert len(resolve) == 1
    assert resolve[0].levelno == logging.WARNING


def test_wire_schedules_write_without_awaiting_it():
    # Guards the reentrancy invariant: the corrective write must be SCHEDULED
    # via spawn, never awaited inline (awaiting inside a subscription callback
    # deadlocks the real client's consumer loop). A spy spawn captures the
    # coroutine without running it, so we can prove on_pic returned first.
    async def scenario():
        client = FakeClient()
        keeper = build_keeper(CFG)
        t = [0.0]
        scheduled = []

        def spy_spawn(coro):
            scheduled.append(coro)  # capture but do NOT schedule/run
            return coro

        on_pic, on_app = wire(keeper, client, clock=lambda: t[0], spawn=spy_spawn)
        await on_pic(_bright())
        t[0] = 10.0
        await on_app("home")     # on-subscribe snapshot: baseline only
        await on_app("netflix")
        t[0] = 10.5
        await on_pic(_dark())
        assert len(scheduled) == 1        # a write was scheduled
        assert client.set_calls == []     # but NOT run inline -> proves spawn, not await
        await scheduled[0]                 # run the captured coroutine now
        assert client.set_calls == [{"pictureMode": "expert1"}]

    asyncio.run(scenario())


def test_load_config_rejects_malformed_fingerprint():
    with pytest.raises(SystemExit):
        load_config(env={"LGTV_HOST": "tv", "LGTV_PRESET_BRIGHT": "oops"})


def test_load_config_lux_defaults_and_overrides():
    cfg = load_config(env={"LGTV_HOST": "tv"})
    assert (cfg.lux_poll_secs, cfg.lux_dark_below, cfg.lux_bright_above,
            cfg.lux_hold_secs) == (30.0, 1.0, 3.0, 30.0)
    tuned = load_config(env={"LGTV_HOST": "tv", "LGTV_LUX_POLL_SECS": "15",
                             "LGTV_LUX_DARK_BELOW": "2", "LGTV_LUX_BRIGHT_ABOVE": "6",
                             "LGTV_LUX_HOLD_SECS": "45"})
    assert (tuned.lux_poll_secs, tuned.lux_dark_below, tuned.lux_bright_above,
            tuned.lux_hold_secs) == (15.0, 2.0, 6.0, 45.0)


from datetime import datetime, timedelta, timezone

from preset_daemon import poll_lux

START = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


class ScriptedSource:
    """Replays a fixed lux sequence, then holds the last value forever."""

    def __init__(self, luxes: list[float]) -> None:
        self._luxes = luxes
        self._i = 0

    async def read(self) -> float:
        lux = self._luxes[min(self._i, len(self._luxes) - 1)]
        self._i += 1
        return lux

    async def close(self) -> None:
        pass


async def drive_lux(luxes, keeper, client, *, cfg=CFG, on_poll=None):
    """Run poll_lux over `luxes`, one poll per element, advancing a datetime
    clock by cfg.lux_poll_secs each poll. `on_poll(n)` can mutate the keeper
    between polls (e.g. simulate a manual change or DV ending)."""
    now = [START]
    polls = [0]

    async def sleep(_secs):
        now[0] = now[0] + timedelta(seconds=cfg.lux_poll_secs)
        polls[0] += 1
        if on_poll is not None:
            on_poll(polls[0])
        if polls[0] >= len(luxes):
            raise StopLoop

    with pytest.raises(StopLoop):
        await poll_lux(ScriptedSource(luxes), keeper, client, cfg,
                       clock=lambda: now[0], sleep=sleep)


def test_lux_applies_dark_immediately_when_room_starts_dark():
    async def scenario():
        client, keeper = FakeClient(), build_keeper(CFG)
        keeper.on_picture_change(_bright(), now=0.0)  # startup seed: current = bright
        await drive_lux([0.0], keeper, client)
        assert client.set_calls == [{"pictureMode": "expert2"}]

    asyncio.run(scenario())


def test_lux_ignores_a_brief_darkening():
    async def scenario():
        client, keeper = FakeClient(), build_keeper(CFG)
        keeper.on_picture_change(_bright(), now=0.0)
        # Bright, one dark poll (< hold), bright again: a passing shadow.
        await drive_lux([50.0, 0.0, 50.0], keeper, client)
        assert client.set_calls == []

    asyncio.run(scenario())


def test_lux_commits_dark_once_it_holds():
    async def scenario():
        client, keeper = FakeClient(), build_keeper(CFG)
        keeper.on_picture_change(_bright(), now=0.0)
        # Two consecutive dark polls span the 30s hold at 30s spacing.
        await drive_lux([50.0, 0.0, 0.0], keeper, client)
        assert client.set_calls == [{"pictureMode": "expert2"}]

    asyncio.run(scenario())


def test_lux_no_write_when_already_on_band():
    async def scenario():
        client, keeper = FakeClient(), build_keeper(CFG)
        keeper.on_picture_change(_dark(), now=0.0)  # already dark by hand
        await drive_lux([0.0], keeper, client)
        assert client.set_calls == []

    asyncio.run(scenario())


def test_lux_never_clobbers_dolby_vision():
    async def scenario():
        client, keeper = FakeClient(), build_keeper(CFG)
        keeper.on_picture_change(_dv(), now=0.0)  # current = UNKNOWN
        await drive_lux([0.0, 0.0, 0.0], keeper, client)
        assert client.set_calls == []

    asyncio.run(scenario())


def test_lux_applies_once_dolby_vision_ends():
    async def scenario():
        client, keeper = FakeClient(), build_keeper(CFG)
        keeper.on_picture_change(_dv(), now=0.0)  # UNKNOWN: deferred

        def on_poll(n):
            if n == 1:  # DV ends, TV back on a known bright preset
                keeper.on_picture_change(_bright(), now=float(n))

        await drive_lux([0.0, 0.0], keeper, client, on_poll=on_poll)
        assert client.set_calls == [{"pictureMode": "expert2"}]

    asyncio.run(scenario())


def test_lux_lets_a_manual_override_ride():
    async def scenario():
        client, keeper = FakeClient(), build_keeper(CFG)
        keeper.on_picture_change(_dark(), now=0.0)  # lux aligns to dark, no write

        def on_poll(n):
            if n == 1:  # user flips to Bright by hand while the room stays dark
                keeper.on_picture_change(_bright(), now=float(n))

        # Dark throughout: lux must not re-impose Dark over the manual Bright.
        await drive_lux([0.0, 0.0, 0.0], keeper, client, on_poll=on_poll)
        assert client.set_calls == []

    asyncio.run(scenario())


class FailOnceClient(FakeClient):
    """Fails the first write, succeeds after — a transient TV blip."""

    def __init__(self) -> None:
        super().__init__()
        self._failed = False

    async def set_settings(self, category: str, settings: dict[str, object]) -> None:
        self.set_calls.append(settings)
        if not self._failed:
            self._failed = True
            raise ConnectionError("blip")


def test_lux_retries_a_failed_write():
    async def scenario():
        client, keeper = FailOnceClient(), build_keeper(CFG)
        keeper.on_picture_change(_bright(), now=0.0)
        # Room dark from the start; first write blips, second lands.
        await drive_lux([0.0, 0.0], keeper, client)
        assert client.set_calls == [{"pictureMode": "expert2"},
                                    {"pictureMode": "expert2"}]

    asyncio.run(scenario())
