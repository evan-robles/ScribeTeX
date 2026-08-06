import pytest
from scribe_tex.classify import parse_date, display_date


@pytest.mark.parametrize("raw,iso", [
    ("2025-10-03", "2025-10-03"),
    ("Oct 3 2025", "2025-10-03"),
    ("October 3, 2025", "2025-10-03"),
    ("10/3/2025", "2025-10-03"),
    ("10/3/25", "2025-10-03"),
])
def test_parse_valid_dates(raw, iso):
    assert parse_date(raw) == iso


@pytest.mark.parametrize("raw", ["3/4", "", "not a date", "someday"])
def test_parse_rejects_ambiguous_or_bad(raw):
    assert parse_date(raw) is None


def test_display_date():
    assert display_date("2025-10-03") == "October 3, 2025"
