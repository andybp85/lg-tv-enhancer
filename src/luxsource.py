"""Pluggable ambient-lux sources behind one async protocol.

The daemon doesn't care whether lux arrives over I2C, from a file, or (later)
HTTP/MQTT — it awaits `LuxSource.read()`. Tests inject a fake. The source is
picked by env (12-factor): `LGTV_LUX_SOURCE=bh1750|file|none`. Unset/none means
the ambient hook is off and the preset daemon behaves exactly as before.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Mapping, Protocol

from smbus2 import SMBus

import bh1750

I2C_BUS = 1  # GPIO2/GPIO3 on every modern Pi header


class LuxSource(Protocol):
    async def read(self) -> float: ...
    async def close(self) -> None: ...


class BH1750Source:
    """BH1750 over I2C. The blocking ~180ms read runs in a worker thread so it
    never stalls the daemon's event loop."""

    def __init__(self, bus: object, address: int = bh1750.DEFAULT_ADDRESS) -> None:
        self._bus = bus
        self._address = address

    async def read(self) -> float:
        return await asyncio.to_thread(bh1750.read_lux, self._bus, self._address)

    async def close(self) -> None:
        self._bus.close()


class FileSource:
    """Reads a lux float from a file each poll — for tests, or a bridge that
    writes a Home Assistant / MQTT lux value to a file for us to pick up."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    async def read(self) -> float:
        return float(self._path.read_text().strip())

    async def close(self) -> None:
        pass


def make_source(env: Mapping[str, str] = os.environ) -> LuxSource | None:
    """Build the configured lux source, or None when the ambient hook is off."""
    kind = env.get("LGTV_LUX_SOURCE", "none").strip().lower()
    if kind in ("", "none"):
        return None
    if kind == "file":
        path = env.get("LGTV_LUX_FILE")
        if not path:
            raise SystemExit("LGTV_LUX_SOURCE=file requires LGTV_LUX_FILE")
        return FileSource(Path(path))
    if kind == "bh1750":
        address = int(env.get("LGTV_LUX_ADDRESS", "0x23"), 0)
        return BH1750Source(SMBus(I2C_BUS), address)
    raise SystemExit(f"unknown LGTV_LUX_SOURCE={kind!r}")
