import asyncio

import pytest

from luxsource import BH1750Source, FileSource, make_source


def run(coro):
    return asyncio.run(coro)


class ClosableBus:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_bh1750_source_reads_through_the_driver(monkeypatch):
    import bh1750

    calls = []

    def fake_read(bus, address, **_):
        calls.append((bus, address))
        return 42.0

    monkeypatch.setattr(bh1750, "read_lux", fake_read)
    source = BH1750Source(bus="BUS", address=0x5C)
    assert run(source.read()) == 42.0
    assert calls == [("BUS", 0x5C)]


def test_bh1750_source_close_releases_bus():
    bus = ClosableBus()
    run(BH1750Source(bus).close())
    assert bus.closed


def test_file_source_reads_current_value(tmp_path):
    path = tmp_path / "lux"
    path.write_text("123.4\n")
    assert run(FileSource(path).read()) == pytest.approx(123.4)


def test_file_source_rereads_each_poll(tmp_path):
    path = tmp_path / "lux"
    path.write_text("1.0")
    source = FileSource(path)
    assert run(source.read()) == 1.0
    path.write_text("99.0")
    assert run(source.read()) == 99.0


def test_make_source_absent_when_unset():
    assert make_source({}) is None
    assert make_source({"LGTV_LUX_SOURCE": "none"}) is None


def test_make_source_file(tmp_path):
    source = make_source({"LGTV_LUX_SOURCE": "file",
                          "LGTV_LUX_FILE": str(tmp_path / "x")})
    assert isinstance(source, FileSource)


def test_make_source_file_requires_path():
    with pytest.raises(SystemExit):
        make_source({"LGTV_LUX_SOURCE": "file"})


def test_make_source_bh1750(monkeypatch):
    import luxsource

    monkeypatch.setattr(luxsource, "SMBus", lambda bus: f"bus{bus}")
    source = make_source({"LGTV_LUX_SOURCE": "bh1750"})
    assert isinstance(source, BH1750Source)


def test_make_source_rejects_unknown_kind():
    with pytest.raises(SystemExit):
        make_source({"LGTV_LUX_SOURCE": "nope"})
