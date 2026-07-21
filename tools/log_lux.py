"""Log ambient lux to CSV so band thresholds come from measurement, not guesses.

Run this for a full day/night cycle in the room the TV lives in, with the
lights used the way they're normally used. The resulting CSV is the input for
choosing dark/dim/bright boundaries and hysteresis widths (lg-tv-enhancer-7f7w).

    venv/bin/python tools/log_lux.py --out lux.csv --interval 10

Ctrl-C to stop; rows are flushed as they're written, so a kill loses nothing
and `tail -f lux.csv` works while it runs.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from smbus2 import SMBus  # noqa: E402

import bh1750  # noqa: E402

I2C_BUS = 1  # GPIO2/GPIO3 on every modern Pi header


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("lux.csv"),
                        help="CSV to append to (default: lux.csv)")
    parser.add_argument("--interval", type=float, default=10.0,
                        help="seconds between readings (default: 10)")
    parser.add_argument("--address", type=lambda s: int(s, 0),
                        default=bh1750.DEFAULT_ADDRESS,
                        help="I2C address (default: 0x23)")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    # Append, so an interrupted run can be resumed into the same dataset.
    is_new = not args.out.exists()
    with args.out.open("a", newline="") as handle, SMBus(I2C_BUS) as bus:
        writer = csv.writer(handle)
        if is_new:
            writer.writerow(["timestamp", "lux"])
        print(f"logging to {args.out} every {args.interval:g}s; Ctrl-C to stop",
              file=sys.stderr)
        while True:
            lux = bh1750.read_lux(bus, args.address)
            writer.writerow([datetime.now().astimezone().isoformat(), f"{lux:.1f}"])
            handle.flush()
            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
