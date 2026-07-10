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
