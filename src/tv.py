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


async def apply_eye_comfort(host: str, client_key: Optional[str], desired: str,
                            *, client_factory=_make_client) -> bool:
    """Reconcile the TV's eyeComfortMode to `desired` ("on" / "off").

    Returns True when the TV already matches or confirms the new value on
    read-back; False when the write didn't stick (e.g. unsupported firmware).
    Raises on connection/request failure — the caller retries next tick.
    """
    client = None
    try:
        client = await asyncio.wait_for(client_factory(host, client_key),
                                        CONNECT_TIMEOUT)
        await asyncio.wait_for(client.connect(), CONNECT_TIMEOUT)
        current = await asyncio.wait_for(
            client.get_picture_settings(keys=[KEY]), REQUEST_TIMEOUT)
        if current.get(KEY) == desired:
            return True
        await asyncio.wait_for(
            client.set_settings(CATEGORY, {KEY: desired}), REQUEST_TIMEOUT)
        readback = await asyncio.wait_for(
            client.get_picture_settings(keys=[KEY]), REQUEST_TIMEOUT)
        ok = readback.get(KEY) == desired
        if not ok:
            log.debug("eyeComfortMode write did not stick: wanted %s, read %s",
                      desired, readback.get(KEY))
        return ok
    finally:
        if client is not None:
            try:
                await asyncio.wait_for(client.disconnect(), DISCONNECT_TIMEOUT)
            except Exception:
                pass
