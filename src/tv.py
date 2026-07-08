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


async def _read_keys(client, keys: list) -> Optional[dict]:
    """Current values for `keys`, or None when this firmware refuses the read.

    The C9's ssap getSystemSettings whitelists readable keys — eyeComfortMode,
    for one, is write-only there ("Some keys are not allowed for the
    request"). Timeouts still propagate: a dead connection must fail the
    whole attempt, not degrade to "blind".
    """
    try:
        return await asyncio.wait_for(
            client.get_picture_settings(keys=keys), REQUEST_TIMEOUT)
    except asyncio.TimeoutError:
        raise
    except Exception as exc:
        log.debug("picture settings %s not readable on this firmware (%s); "
                  "writing blind", keys, exc)
        return None


def _matches(current: dict, settings: dict) -> bool:
    # webOS stores numeric picture values as strings ("-50"); compare as str
    return all(str(current.get(k)) == str(v) for k, v in settings.items())


async def apply_picture_settings(host: str, client_key: Optional[str],
                                 settings: dict, *,
                                 client_factory=_make_client) -> bool:
    """Reconcile `"picture"`-category settings to the given values.

    Returns True when the TV already matches, confirms the values on
    read-back, or accepted the write on firmware where the keys are not
    readable (C9) — there the luna write is trusted. Returns False only on
    a read-back mismatch. Raises on connection/request failure — the caller
    retries next tick.
    """
    client = None
    try:
        client = await asyncio.wait_for(client_factory(host, client_key),
                                        CONNECT_TIMEOUT)
        await asyncio.wait_for(client.connect(), CONNECT_TIMEOUT)
        keys = list(settings)
        current = await _read_keys(client, keys)
        if current is not None and _matches(current, settings):
            return True
        await asyncio.wait_for(
            client.set_settings(CATEGORY, settings), REQUEST_TIMEOUT)
        if current is None:
            return True
        readback = await _read_keys(client, keys)
        ok = readback is None or _matches(readback, settings)
        if not ok:
            log.debug("picture write did not stick: wanted %s, read %s",
                      settings, readback)
        return ok
    finally:
        if client is not None:
            try:
                await asyncio.wait_for(client.disconnect(), DISCONNECT_TIMEOUT)
            except Exception:
                pass


async def apply_eye_comfort(host: str, client_key: Optional[str], desired: str,
                            *, client_factory=_make_client) -> bool:
    """Reconcile the TV's eyeComfortMode to `desired` ("on" / "off")."""
    return await apply_picture_settings(host, client_key, {KEY: desired},
                                        client_factory=client_factory)
