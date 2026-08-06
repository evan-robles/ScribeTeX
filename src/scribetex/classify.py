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


def course_slug(name: str) -> str:
    """Folder-safe slug for a course name."""
    cleaned = re.sub(r"[^A-Za-z0-9\s-]", "", name)
    parts = cleaned.split()
    return "-".join(parts)


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[\s]+", s.lower()) if t}


def match_course(hint: str, known: list[str]) -> tuple[str | None, str]:
    """Match a free-text course hint to a known course name.

    Returns (course_or_None, confidence in {"high","low","none"}).
    """
    hint_tokens = _tokens(hint)
    if not hint_tokens:
        return None, "none"
    for course in known:
        if course.strip().lower() == hint.strip().lower():
            return course, "high"
    scored = []
    for course in known:
        overlap = hint_tokens & _tokens(course)
        if overlap:
            scored.append((len(overlap), course))
    if not scored:
        return None, "none"
    scored.sort(reverse=True)
    top_score = scored[0][0]
    winners = [c for s, c in scored if s == top_score]
    if len(winners) == 1:
        # Distinguish a strong match (a distinctive token like a course number)
        # from a weak one (a single common word).
        confidence = "high" if top_score >= 2 or any(
            any(ch.isdigit() for ch in tok) for tok in (hint_tokens & _tokens(winners[0]))
        ) else "low"
        if confidence == "high":
            return winners[0], confidence
        else:
            return None, "none"
    return None, "low"
