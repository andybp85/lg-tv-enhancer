import asyncio

import pytest

from tv import KEY, apply_eye_comfort, apply_picture_settings


class ReadRefused(Exception):
    """The C9 firmware's answer to a getSystemSettings for this key."""


class FakeClient:
    """Stands in for bscpylgtv's WebOsClient; records the calls made."""

    def __init__(self, initial="off", sticks=True, fail_connect=False,
                 read_refused=False):
        self.settings = {KEY: initial}
        self.sticks = sticks
        self.fail_connect = fail_connect
        self.read_refused = read_refused
        self.set_calls = []
        self.disconnected = False

    async def connect(self):
        if self.fail_connect:
            raise ConnectionRefusedError("TV off")

    async def disconnect(self):
        self.disconnected = True

    async def get_picture_settings(self, keys):
        if self.read_refused:
            raise ReadRefused("Some keys are not allowed for the request. "
                              "( eyeComfortMode )")
        return {k: self.settings[k] for k in keys}

    async def set_settings(self, category, settings):
        assert category == "picture"
        self.set_calls.append(settings)
        if self.sticks:
            self.settings.update(settings)


def factory_for(client):
    async def factory(host, key):
        return client
    return factory


def apply_with(client, desired):
    return asyncio.run(apply_eye_comfort(
        "10.0.0.2", "key", desired, client_factory=factory_for(client)))


def test_sets_and_verifies():
    client = FakeClient(initial="off")
    assert apply_with(client, "on") is True
    assert client.set_calls == [{KEY: "on"}]
    assert client.disconnected


def test_already_matching_skips_write():
    client = FakeClient(initial="on")
    assert apply_with(client, "on") is True
    assert client.set_calls == []


def test_write_that_does_not_stick_returns_false():
    client = FakeClient(initial="off", sticks=False)
    assert apply_with(client, "on") is False


def test_numeric_settings_compared_as_strings():
    # webOS stores slider values as strings ("-30"); a matching current value
    # must short-circuit the write even though types differ
    client = FakeClient()
    client.settings["colorTemperature"] = "-30"
    ok = asyncio.run(apply_picture_settings(
        "10.0.0.2", "key", {"colorTemperature": -30},
        client_factory=factory_for(client)))
    assert ok is True
    assert client.set_calls == []


def test_read_refused_writes_blind_and_trusts_the_write():
    # C9: eyeComfortMode is write-only via ssap GET (lg-tv-enhancer-ccuj)
    client = FakeClient(initial="off", read_refused=True)
    assert apply_with(client, "on") is True
    assert client.set_calls == [{KEY: "on"}]


def test_read_refused_write_failure_still_raises():
    client = FakeClient(read_refused=True)

    async def broken_set(category, settings):
        raise ConnectionResetError("connection dropped mid-write")
    client.set_settings = broken_set
    with pytest.raises(ConnectionResetError):
        apply_with(client, "on")
    assert client.disconnected


def test_connect_failure_raises_and_still_disconnects():
    client = FakeClient(fail_connect=True)
    with pytest.raises(ConnectionRefusedError):
        apply_with(client, "on")
    assert client.disconnected
