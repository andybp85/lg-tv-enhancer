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
             bright_mode="expert1", dark_mode="expert2", settle_secs=3.0)


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

        async def flaky_serve(cfg):
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
