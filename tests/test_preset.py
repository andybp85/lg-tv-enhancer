import pytest

from preset import (
    BRIGHT,
    DARK,
    UNKNOWN,
    classify,
    fingerprint_of,
    parse_fingerprint,
    parse_fingerprints,
)

BRIGHT_FPS = frozenset({(90, 90, 65)})
DARK_FPS = frozenset({(85, 10, 50)})


def bright_settings() -> dict[str, object]:
    return {"contrast": 90, "backlight": 90, "brightness": 65, "color": "50"}


def dark_settings() -> dict[str, object]:
    # Deliberately mixed str/int, as the TV sends them.
    return {"contrast": "85", "backlight": 10, "brightness": "50", "color": "50"}


def dv_settings() -> dict[str, object]:
    return {"contrast": 90, "backlight": 90, "brightness": 60, "color": "50"}


def xfinity_bright_settings() -> dict[str, object]:
    # Same preset, different per-input calibration than the apps (backlight 100).
    return {"contrast": 90, "backlight": 100, "brightness": 60, "color": "50"}


def test_parse_fingerprint():
    assert parse_fingerprint("90,90,65") == (90, 90, 65)
    assert parse_fingerprint(" 85, 10 ,50 ") == (85, 10, 50)


def test_parse_fingerprint_rejects_wrong_arity():
    with pytest.raises(ValueError):
        parse_fingerprint("90,90")


def test_parse_fingerprints_single_and_multi():
    assert parse_fingerprints("90,90,65") == frozenset({(90, 90, 65)})
    assert parse_fingerprints("90,90,65;90,100,60") == frozenset(
        {(90, 90, 65), (90, 100, 60)})


def test_fingerprint_of_casts_mixed_types():
    assert fingerprint_of(dark_settings()) == (85, 10, 50)


def test_fingerprint_of_missing_key_returns_none():
    assert fingerprint_of({"contrast": 90, "backlight": 90}) is None


def test_classify_bright():
    assert classify(bright_settings(), bright=BRIGHT_FPS, dark=DARK_FPS) == BRIGHT


def test_classify_dark_with_string_values():
    assert classify(dark_settings(), bright=BRIGHT_FPS, dark=DARK_FPS) == DARK


def test_classify_dolby_vision_is_unknown():
    # DV (90,90,60) differs from Bright (90,90,65) only in brightness.
    assert classify(dv_settings(), bright=BRIGHT_FPS, dark=DARK_FPS) == UNKNOWN


def test_classify_matches_any_fingerprint_in_the_set():
    # Per-input calibration: an app Bright and the Xfinity Bright are both bright.
    bright = frozenset({(90, 90, 65), (90, 100, 60)})
    assert classify(bright_settings(), bright=bright, dark=DARK_FPS) == BRIGHT
    assert classify(xfinity_bright_settings(), bright=bright, dark=DARK_FPS) == BRIGHT
    # And a set-member Xfinity Bright must not be mistaken for DV (90,90,60).
    assert classify(dv_settings(), bright=bright, dark=DARK_FPS) == UNKNOWN


from preset import Correction, Keeper


def make_keeper() -> Keeper:
    return Keeper(bright_fps=BRIGHT_FPS, dark_fps=DARK_FPS,
                  bright_mode="expert1", dark_mode="expert2", settle_secs=3.0)


def app_switch(k: Keeper, now: float) -> None:
    """A genuine app switch, preceded by the on-subscribe snapshot.

    Production never sees a switch as the first app event: subscribing pushes
    the foreground app immediately, and only a later, different id is a real
    switch. Tests that want an armed settle window go through both.
    """
    k.on_app_change("home", now)      # snapshot: baseline only, never arms
    k.on_app_change("netflix", now)   # switch away from it: arms the window


def test_app_flip_bright_to_dark_restores_bright():
    k = make_keeper()
    assert k.on_picture_change(bright_settings(), now=0.0) is None  # seed current = bright
    app_switch(k, now=10.0)
    correction = k.on_picture_change(dark_settings(), now=10.5)
    assert correction == Correction(mode="expert1", to_preset=BRIGHT)


def test_app_flip_dark_to_bright_restores_dark():
    k = make_keeper()
    k.on_picture_change(dark_settings(), now=0.0)
    app_switch(k, now=10.0)
    correction = k.on_picture_change(bright_settings(), now=10.2)
    assert correction == Correction(mode="expert2", to_preset=DARK)


def test_same_preset_after_app_change_no_correction():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    app_switch(k, now=10.0)
    # No mode change means no picture event fires; nothing to correct. If the TV
    # does re-emit the same fingerprint, it must not trigger a write.
    assert k.on_picture_change(bright_settings(), now=10.3) is None


def test_manual_change_without_app_change_is_not_corrected():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    # User deliberately flips Bright -> Dark with no app switch: no correction,
    # and Dark becomes the new sticky value.
    assert k.on_picture_change(dark_settings(), now=100.0) is None
    app_switch(k, now=101.0)
    correction = k.on_picture_change(bright_settings(), now=101.2)
    assert correction == Correction(mode="expert2", to_preset=DARK)


def test_app_change_into_dolby_vision_is_left_alone():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    app_switch(k, now=5.0)
    assert k.on_picture_change(dv_settings(), now=5.3) is None  # after = UNKNOWN


def test_coming_from_dolby_vision_is_left_alone():
    k = make_keeper()
    k.on_picture_change(dv_settings(), now=0.0)  # current = UNKNOWN
    app_switch(k, now=5.0)
    assert k.on_picture_change(dark_settings(), now=5.2) is None  # before = UNKNOWN


def test_picture_event_after_window_expiry_is_manual():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    app_switch(k, now=10.0)  # window closes at 13.0
    assert k.on_picture_change(dark_settings(), now=20.0) is None


def test_corrective_write_event_does_not_loop():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    app_switch(k, now=10.0)
    assert k.on_picture_change(dark_settings(), now=10.5) is not None  # correction issued
    # The write flips the TV back to bright, producing this event; must be inert.
    assert k.on_picture_change(bright_settings(), now=10.6) is None


def test_lux_desires_dark_from_bright_yields_correction():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)  # current = bright
    assert k.set_desired(DARK) == Correction(mode="expert2", to_preset=DARK)


def test_lux_desires_bright_from_dark_yields_correction():
    k = make_keeper()
    k.on_picture_change(dark_settings(), now=0.0)
    assert k.set_desired(BRIGHT) == Correction(mode="expert1", to_preset=BRIGHT)


def test_lux_desiring_current_band_is_a_noop():
    # Already on the wanted preset (e.g. set by hand): no redundant blind-write.
    k = make_keeper()
    k.on_picture_change(dark_settings(), now=0.0)
    assert k.set_desired(DARK) is None


def test_lux_does_not_clobber_an_unknown_preset():
    # Dolby Vision (or any unrecognized preset) is hands-off, even for lux —
    # the room going dark must not force ISF over DV.
    k = make_keeper()
    k.on_picture_change(dv_settings(), now=0.0)  # current = UNKNOWN
    assert k.set_desired(DARK) is None


def test_lux_write_event_is_inert():
    # The write lux triggers comes back as a picture event with no app window;
    # it must just update tracked state, not cause a correction.
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    assert k.set_desired(DARK) is not None
    assert k.on_picture_change(dark_settings(), now=1.0) is None
    # And now Dark is the tracked preset, so lux wanting Dark is a no-op.
    assert k.set_desired(DARK) is None


def test_lux_commit_inside_the_settle_window_is_not_reverted():
    # A band commit can land within settle_secs of a genuine app switch. The
    # write is ours, so its echo must not be read as an app-induced flip
    # (lg-tv-enhancer-9x3h).
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)  # current = bright
    app_switch(k, now=10.0)                          # real switch, window to 13.0
    assert k.set_desired(DARK) is not None           # lux commits dark mid-window
    assert k.on_picture_change(dark_settings(), now=10.5) is None


def test_window_protects_the_lux_band_after_our_write_lands():
    # Once lux deliberately changes the preset mid-window, the preset worth
    # restoring is the new one — not the stale snapshot from the app switch.
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    app_switch(k, now=10.0)
    k.set_desired(DARK)
    assert k.on_picture_change(dark_settings(), now=10.5) is None  # our echo
    correction = k.on_picture_change(bright_settings(), now=11.0)
    assert correction == Correction(mode="expert2", to_preset=DARK)


def test_a_failed_write_does_not_swallow_a_later_unrelated_flip():
    # If the write never lands, the expectation is spent on the next picture
    # event regardless, so it cannot linger and mask corrections forever.
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    k.set_desired(DARK)                              # suppose this write fails
    k.on_picture_change(bright_settings(), now=1.0)  # unrelated event spends it
    app_switch(k, now=10.0)
    correction = k.on_picture_change(dark_settings(), now=10.5)
    assert correction == Correction(mode="expert1", to_preset=BRIGHT)


def test_first_app_observation_does_not_arm_the_window():
    # Subscribing to current_app delivers the foreground app immediately. That
    # push is a snapshot, not a switch, so it must not arm a settle window: the
    # lux hook's first apply lands inside it and would be read as a flip
    # (lg-tv-enhancer-mtin).
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)  # current = bright
    k.on_app_change("netflix", now=0.1)              # on-subscribe snapshot
    assert k.set_desired(DARK) is not None            # lux wants dark, writes it
    assert k.on_picture_change(dark_settings(), now=0.2) is None


def test_real_app_change_after_the_first_observation_still_corrects():
    # The snapshot only establishes the baseline; a genuine switch away from it
    # must still arm the window and correct a flip.
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    k.on_app_change("netflix", now=0.1)   # snapshot: baseline only
    k.on_app_change("youtube", now=10.0)  # real switch: arms the window
    correction = k.on_picture_change(dark_settings(), now=10.5)
    assert correction == Correction(mode="expert1", to_preset=BRIGHT)


def test_repeated_same_app_event_does_not_arm_the_window():
    # The TV re-emits the current app on reconnect-ish events; same app id is
    # not a switch, so a picture change after it is manual, not a flip.
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    k.on_app_change("netflix", now=0.1)
    k.on_app_change("netflix", now=10.0)
    assert k.on_picture_change(dark_settings(), now=10.5) is None
