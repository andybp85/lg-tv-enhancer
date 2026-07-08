"""Set the LG C9's Eye Comfort Mode over the webOS LAN API (bscpylgtv).

`eyeComfortMode` lives in the `"picture"` settings category and is written via
the luna `set_settings` path (bscpylgtv docs/available_settings_C9.md). Every
webOS await is wrapped in a timeout: this TV can drop off the network without
closing TCP, and an unguarded await then hangs near-forever (see tv-dsp's
dead-connection guards, tv-dsp-0iqm).

Connections are ephemeral — connect, reconcile, disconnect — so the daemon
holds no session while idle and each attempt starts from a clean slate.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

log = logging.getLogger(__name__)

CATEGORY = "picture"
KEY = "eyeComfortMode"

CONNECT_TIMEOUT = 15.0
REQUEST_TIMEOUT = 10.0
DISCONNECT_TIMEOUT = 5.0


async def _make_client(host: str, client_key: Optional[str]):
    from bscpylgtv import WebOsClient  # lazy: tests run without the package
    return await WebOsClient.create(host, client_key=client_key,
                                    states=[], ping_interval=None)


async def _read_mode(client) -> Optional[str]:
    """Current eyeComfortMode, or None when this firmware refuses the read.

    The C9's ssap getSystemSettings whitelists readable keys and
    eyeComfortMode is not on it ("Some keys are not allowed for the
    request") — the key is write-only there. Timeouts still propagate:
    a dead connection must fail the whole attempt, not degrade to "blind".
    """
    try:
        current = await asyncio.wait_for(
            client.get_picture_settings(keys=[KEY]), REQUEST_TIMEOUT)
        return current.get(KEY)
    except asyncio.TimeoutError:
        raise
    except Exception as exc:
        log.debug("eyeComfortMode not readable on this firmware (%s); "
                  "writing blind", exc)
        return None


async def apply_eye_comfort(host: str, client_key: Optional[str], desired: str,
                            *, client_factory=_make_client) -> bool:
    """Reconcile the TV's eyeComfortMode to `desired` ("on" / "off").

    Returns True when the TV already matches, confirms the new value on
    read-back, or accepted the write on firmware where the key is not
    readable (C9) — there the luna write is trusted. Returns False only on
    a read-back mismatch. Raises on connection/request failure — the caller
    retries next tick.
    """
    client = None
    try:
        client = await asyncio.wait_for(client_factory(host, client_key),
                                        CONNECT_TIMEOUT)
        await asyncio.wait_for(client.connect(), CONNECT_TIMEOUT)
        current = await _read_mode(client)
        if current == desired:
            return True
        await asyncio.wait_for(
            client.set_settings(CATEGORY, {KEY: desired}), REQUEST_TIMEOUT)
        if current is None:
            return True
        readback = await _read_mode(client)
        ok = readback in (None, desired)
        if not ok:
            log.debug("eyeComfortMode write did not stick: wanted %s, read %s",
                      desired, readback)
        return ok
    finally:
        if client is not None:
            try:
                await asyncio.wait_for(client.disconnect(), DISCONNECT_TIMEOUT)
            except Exception:
                pass
