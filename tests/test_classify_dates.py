import pytest
from scribetex.classify import parse_date, display_date


@pytest.mark.parametrize("raw,iso", [
    ("2025-10-03", "2025-10-03"),
    ("Oct 3 2025", "2025-10-03"),
    ("October 3, 2025", "2025-10-03"),
    ("10/3/2025", "2025-10-03"),
    ("10/3/25", "2025-10-03"),
])
def test_parse_valid_dates(raw, iso):
    assert parse_date(raw) == iso


@pytest.mark.parametrize("raw", ["3/4", "10/3", "", "not a date", "someday"])
def test_parse_rejects_ambiguous_or_bad(raw):
    assert parse_date(raw) is None


@pytest.mark.parametrize("raw", [
    "Lecture 15",     # stray number in note header, not a date
    "Room 12",
    "Chapter 42",
    "week 3",
    "2025",           # bare year: day/month would be default-filled
    "October",        # month only
    "Oct 2025",       # month + year, no day
    "12",
])
def test_parse_rejects_nondate_text(raw):
    # Untrusted note text must not be coerced into a confident wrong date.
    assert parse_date(raw) is None


def test_parse_rejects_implausible_year():
    assert parse_date("Oct 3 1850") is None
    assert parse_date("Jan 1 3000") is None


def test_display_date():
    assert display_date("2025-10-03") == "October 3, 2025"
