"""Course-hint matching and date parsing/normalization."""
from __future__ import annotations
import re
from datetime import datetime
from dateutil import parser as _dateparser

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_date(raw: str) -> str | None:
    """Normalize a human date string to ISO YYYY-MM-DD, or None if unusable.

    Requires an explicit year (rejects bare '3/4'). Uses month-first (US)
    interpretation for slash dates, matching how the user writes dates.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    if _ISO_RE.match(raw):
        return raw
    # Require a 4-digit or 2-digit year token to be present somewhere.
    if not re.search(r"\d{2,4}", raw):
        return None
    # Reject two-part slash dates with no year, e.g. "10/3", "12/25".
    slash = raw.split("/")
    if len(slash) == 2:
        return None
    try:
        dt = _dateparser.parse(raw, dayfirst=False, yearfirst=False,
                               default=datetime(1900, 1, 1))
    except (ValueError, OverflowError):
        return None
    # dateutil fills missing pieces from `default`; if year stayed 1900 and the
    # input never mentioned 1900, treat as ambiguous.
    if dt.year == 1900 and "1900" not in raw:
        return None
    return dt.strftime("%Y-%m-%d")


def display_date(iso: str) -> str:
    """ISO YYYY-MM-DD -> 'Month D, YYYY' (no zero-padded day)."""
    dt = datetime.strptime(iso, "%Y-%m-%d")
    return f"{dt:%B} {dt.day}, {dt.year}"
