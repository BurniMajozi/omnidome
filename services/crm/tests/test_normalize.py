import pytest

from services.crm.normalize import (
    LEAD_STATUSES,
    normalize_email,
    normalize_phone,
    normalize_status,
    status_key,
)


@pytest.mark.parametrize("raw,expected", [
    ("0821234567", "+27821234567"),
    ("082 123 4567", "+27821234567"),
    ("082-123-4567", "+27821234567"),
    ("(082) 123 4567", "+27821234567"),
    ("+27821234567", "+27821234567"),
    ("27821234567", "+27821234567"),
    ("+27 82 123 4567", "+27821234567"),
    ("0027821234567", "+27821234567"),
    ("+270821234567", "+27821234567"),
    ("821234567", "+27821234567"),
    ("  0821234567 ext 12 ", "+27821234567"),
    ("011 555 1234", "+27115551234"),
    ("+44 7911 123456", "+447911123456"),
    ("0044 7911 123456", "+447911123456"),
    ("+1 (415) 555-2671", "+14155552671"),
    ("", None),
    (None, None),
    ("abc", None),
    ("12345", None),
    ("082123", None),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_phone_variants_collapse_to_one_key():
    keys = {normalize_phone(v) for v in ["0821234567", "082 123 4567", "+27821234567", "27821234567"]}
    assert keys == {"+27821234567"}


@pytest.mark.parametrize("raw,expected", [
    ("  Jane@Example.COM ", "jane@example.com"), ("", None), ("   ", None), (None, None), ("a@b.co", "a@b.co"),
])
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected


def test_status_normalisation():
    assert normalize_status(" converted ") == "CONVERTED"
    assert normalize_status("Lost") == "LOST"
    assert normalize_status(None) is None
    assert status_key(None) == "" and status_key(" new") == "NEW"
    with pytest.raises(ValueError):
        normalize_status("bogus")
    assert {"NEW", "CONTACTED", "QUALIFIED", "CONVERTED", "LOST", "WON"} <= LEAD_STATUSES
