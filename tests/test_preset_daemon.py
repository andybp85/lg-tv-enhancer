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
        await on_app("netflix")
        t[0] = 10.5
        await on_pic(_dark())            # TV flipped to dark -> correct
        await asyncio.sleep(0)           # let the spawned write task run
        assert client.set_calls == [{"pictureMode": "expert1"}]

    asyncio.run(scenario())


def test_wire_leaves_dolby_vision_alone():
    async def scenario():
        client = FakeClient()
        keeper = build_keeper(CFG)
        t = [0.0]
        on_pic, on_app = wire(keeper, client, clock=lambda: t[0])
        await on_pic(_bright())
        t[0] = 5.0
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

        async def flaky_serve(cfg, *, source=None):
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
