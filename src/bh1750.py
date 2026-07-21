"""BH1750FVI ambient-light sensor over I2C. The one place that touches the bus.

One-shot high-resolution mode: the chip takes a single measurement then powers
itself down, so a slow poll costs almost no current and needs no reset between
reads. Reads are raw 2-byte transfers with no register address — hence i2c_rdwr
rather than the usual read_i2c_block_data, which would prepend a command byte
the sensor reads as an instruction.

Datasheet: https://www.mouser.com/datasheet/2/348/bh1750fvi-e-186247.pdf
"""
from __future__ import annotations

import time

from smbus2 import SMBus, i2c_msg

# ADDR pin low or floating; tie ADDR high for 0x5C to run two on one bus.
DEFAULT_ADDRESS = 0x23

_ONE_TIME_HIGH_RES = 0x20

# Datasheet: H-resolution mode measures in 120ms typical, 180ms max.
_MEASURE_SECS = 0.18

# Raw counts per lux at the default sensitivity.
_COUNTS_PER_LUX = 1.2


def decode_lux(high: int, low: int) -> float:
    """Convert the sensor's big-endian 2-byte reading to lux."""
    return ((high << 8) | low) / _COUNTS_PER_LUX


def read_lux(bus: SMBus, address: int = DEFAULT_ADDRESS, *,
             sleep=time.sleep) -> float:
    """Take one high-resolution measurement. Blocks ~180ms."""
    bus.write_byte(address, _ONE_TIME_HIGH_RES)
    sleep(_MEASURE_SECS)
    reading = i2c_msg.read(address, 2)
    bus.i2c_rdwr(reading)
    high, low = list(reading)
    return decode_lux(high, low)
