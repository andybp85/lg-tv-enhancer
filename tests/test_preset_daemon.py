import pytest

from preset_daemon import Config, load_config


def test_load_config_requires_host():
    with pytest.raises(SystemExit):
        load_config(env={})


def test_load_config_defaults():
    cfg = load_config(env={"LGTV_HOST": "tv"})
    assert cfg.key is None
    assert cfg.bright_fp == (90, 90, 65)
    assert cfg.dark_fp == (85, 10, 50)
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
    assert cfg.bright_fp == (88, 92, 66)
    assert cfg.dark_fp == (80, 5, 48)
    assert cfg.bright_mode == "expert2"
    assert cfg.settle_secs == 5.0


import asyncio

from preset_daemon import build_keeper, wire


class FakeClient:
    """Records pictureMode writes; stands in for bscpylgtv's WebOsClient."""

    def __init__(self) -> None:
        self.set_calls: list[dict[str, object]] = []

    async def set_settings(self, category: str, settings: dict[str, object]) -> None:
        assert category == "picture"
        self.set_calls.append(settings)


CFG = Config(host="tv", key="k", bright_fp=(90, 90, 65), dark_fp=(85, 10, 50),
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
