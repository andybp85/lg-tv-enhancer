import pytest

from preset import (
    BRIGHT,
    DARK,
    UNKNOWN,
    classify,
    fingerprint_of,
    parse_fingerprint,
)

BRIGHT_FP = (90, 90, 65)
DARK_FP = (85, 10, 50)


def bright_settings() -> dict[str, object]:
    return {"contrast": 90, "backlight": 90, "brightness": 65, "color": "50"}


def dark_settings() -> dict[str, object]:
    # Deliberately mixed str/int, as the TV sends them.
    return {"contrast": "85", "backlight": 10, "brightness": "50", "color": "50"}


def dv_settings() -> dict[str, object]:
    return {"contrast": 90, "backlight": 90, "brightness": 60, "color": "50"}


def test_parse_fingerprint():
    assert parse_fingerprint("90,90,65") == (90, 90, 65)
    assert parse_fingerprint(" 85, 10 ,50 ") == (85, 10, 50)


def test_parse_fingerprint_rejects_wrong_arity():
    with pytest.raises(ValueError):
        parse_fingerprint("90,90")


def test_fingerprint_of_casts_mixed_types():
    assert fingerprint_of(dark_settings()) == (85, 10, 50)


def test_fingerprint_of_missing_key_returns_none():
    assert fingerprint_of({"contrast": 90, "backlight": 90}) is None


def test_classify_bright():
    assert classify(bright_settings(), bright=BRIGHT_FP, dark=DARK_FP) == BRIGHT


def test_classify_dark_with_string_values():
    assert classify(dark_settings(), bright=BRIGHT_FP, dark=DARK_FP) == DARK


def test_classify_dolby_vision_is_unknown():
    # DV (90,90,60) differs from Bright (90,90,65) only in brightness.
    assert classify(dv_settings(), bright=BRIGHT_FP, dark=DARK_FP) == UNKNOWN


from preset import Correction, Keeper


def make_keeper() -> Keeper:
    return Keeper(bright_fp=BRIGHT_FP, dark_fp=DARK_FP,
                  bright_mode="expert1", dark_mode="expert2", settle_secs=3.0)


def test_app_flip_bright_to_dark_restores_bright():
    k = make_keeper()
    assert k.on_picture_change(bright_settings(), now=0.0) is None  # seed current = bright
    k.on_app_change(now=10.0)
    correction = k.on_picture_change(dark_settings(), now=10.5)
    assert correction == Correction(mode="expert1", to_preset=BRIGHT)


def test_app_flip_dark_to_bright_restores_dark():
    k = make_keeper()
    k.on_picture_change(dark_settings(), now=0.0)
    k.on_app_change(now=10.0)
    correction = k.on_picture_change(bright_settings(), now=10.2)
    assert correction == Correction(mode="expert2", to_preset=DARK)


def test_same_preset_after_app_change_no_correction():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    k.on_app_change(now=10.0)
    # No mode change means no picture event fires; nothing to correct. If the TV
    # does re-emit the same fingerprint, it must not trigger a write.
    assert k.on_picture_change(bright_settings(), now=10.3) is None


def test_manual_change_without_app_change_is_not_corrected():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    # User deliberately flips Bright -> Dark with no app switch: no correction,
    # and Dark becomes the new sticky value.
    assert k.on_picture_change(dark_settings(), now=100.0) is None
    k.on_app_change(now=101.0)
    correction = k.on_picture_change(bright_settings(), now=101.2)
    assert correction == Correction(mode="expert2", to_preset=DARK)


def test_app_change_into_dolby_vision_is_left_alone():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    k.on_app_change(now=5.0)
    assert k.on_picture_change(dv_settings(), now=5.3) is None  # after = UNKNOWN


def test_coming_from_dolby_vision_is_left_alone():
    k = make_keeper()
    k.on_picture_change(dv_settings(), now=0.0)  # current = UNKNOWN
    k.on_app_change(now=5.0)
    assert k.on_picture_change(dark_settings(), now=5.2) is None  # before = UNKNOWN


def test_picture_event_after_window_expiry_is_manual():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    k.on_app_change(now=10.0)  # window closes at 13.0
    assert k.on_picture_change(dark_settings(), now=20.0) is None


def test_corrective_write_event_does_not_loop():
    k = make_keeper()
    k.on_picture_change(bright_settings(), now=0.0)
    k.on_app_change(now=10.0)
    assert k.on_picture_change(dark_settings(), now=10.5) is not None  # correction issued
    # The write flips the TV back to bright, producing this event; must be inert.
    assert k.on_picture_change(bright_settings(), now=10.6) is None
