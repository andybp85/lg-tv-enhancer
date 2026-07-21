import pytest

from bh1750 import DEFAULT_ADDRESS, decode_lux, read_lux


class FakeBus:
    """Records the command byte and serves canned bytes to the raw read."""

    def __init__(self, reading: tuple[int, int]):
        self.reading = reading
        self.commands: list[tuple[int, int]] = []

    def write_byte(self, address, command):
        self.commands.append((address, command))

    def i2c_rdwr(self, message):
        message.fill(self.reading)


class FakeMessage:
    def __init__(self):
        self.data: tuple[int, int] | None = None

    def fill(self, reading):
        self.data = reading

    def __iter__(self):
        return iter(self.data)


@pytest.fixture
def fake_read(monkeypatch):
    """Replace smbus2's i2c_msg.read so no hardware is needed."""
    import bh1750

    monkeypatch.setattr(bh1750.i2c_msg, "read",
                        staticmethod(lambda address, length: FakeMessage()))


def test_decode_darkness():
    assert decode_lux(0x00, 0x00) == 0.0


def test_decode_scales_by_datasheet_constant():
    # 0x0060 == 96 counts; 96 / 1.2 == 80 lux
    assert decode_lux(0x00, 0x60) == pytest.approx(80.0)


def test_decode_is_big_endian():
    # High byte must dominate: 0x0100 is 256 counts, not 1.
    assert decode_lux(0x01, 0x00) > decode_lux(0x00, 0xFF)


def test_decode_full_scale():
    # 0xFFFF is the sensor's ceiling, ~54612 lux — direct sunlight territory.
    assert decode_lux(0xFF, 0xFF) == pytest.approx(54612.5)


def test_read_lux_triggers_one_shot_measurement(fake_read):
    bus = FakeBus((0x00, 0x60))
    lux = read_lux(bus, sleep=lambda _: None)
    assert lux == pytest.approx(80.0)
    assert bus.commands == [(DEFAULT_ADDRESS, 0x20)]


def test_read_lux_honors_address(fake_read):
    bus = FakeBus((0x00, 0x00))
    read_lux(bus, 0x5C, sleep=lambda _: None)
    assert bus.commands == [(0x5C, 0x20)]


def test_read_lux_waits_for_conversion(fake_read):
    """The 180ms settle is not optional — reading early returns a stale value."""
    bus = FakeBus((0x00, 0x60))
    slept = []
    read_lux(bus, sleep=slept.append)
    assert slept == [pytest.approx(0.18)]
