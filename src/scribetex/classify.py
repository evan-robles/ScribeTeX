"""Course-hint matching and date parsing/normalization."""
from __future__ import annotations
import re
from datetime import datetime
from dateutil import parser as _dateparser

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# A plausible academic-note year range; anything outside is almost certainly a
# misparse of non-date text (e.g. "Chapter 2005" or an OCR artifact).
_MIN_YEAR = 1990
_MAX_YEAR = 2100


def parse_date(raw: str) -> str | None:
    """Normalize a human date string to ISO YYYY-MM-DD, or None if unusable.

    Deliberately strict, because the input is untrusted note text: a note header
    like "Lecture 15" or "Room 12" must NOT be coerced into a confident-but-wrong
    date. Requires an explicit 4-digit year to be present, requires dateutil to
    find a real month AND day (not fill them from the default), and bounds the
    year to a plausible range. Uses month-first (US) interpretation for slash
    dates, matching how the user writes them.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    if _ISO_RE.match(raw):
        return raw
    # Reject a two-part slash date with no year, e.g. "10/3" (month/day only).
    if len(raw.split("/")) == 2:
        return None
    # Parse twice with different defaults; any field that CHANGES between the two
    # was filled from the default (not actually present in the input), so the
    # date is incomplete/ambiguous — reject it. This is the key guard: it lets a
    # full date like "10/3/25" or "Oct 3 2025" through (all fields present, so
    # stable) while rejecting a bare "2025" (day/month default-filled) and a
    # lone token like "Lecture 15"/"Room 12" (which dateutil can't parse at all).
    try:
        d1 = _dateparser.parse(raw, dayfirst=False, yearfirst=False,
                               default=datetime(1900, 1, 1))
        d2 = _dateparser.parse(raw, dayfirst=False, yearfirst=False,
                               default=datetime(2000, 6, 15))
    except (ValueError, OverflowError, TypeError):
        return None
    if (d1.year, d1.month, d1.day) != (d2.year, d2.month, d2.day):
        return None  # a field was default-filled, i.e. not really in the text
    if not (_MIN_YEAR <= d1.year <= _MAX_YEAR):
        return None
    return d1.strftime("%Y-%m-%d")


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
