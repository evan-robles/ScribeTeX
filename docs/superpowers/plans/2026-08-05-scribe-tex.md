# scribe-tex Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastMCP server that files agent-transcribed handwritten notes into per-course LaTeX documents as correctly-ordered, dated `\section`s.

**Architecture:** The server is pure/offline: it renders note pages to PNGs, hands the calling agent a transcription brief, then (after the agent transcribes and the user confirms) inserts the LaTeX into a per-course `main.tex` in date order. All AI (vision transcription) lives in the calling agent; the server does deterministic file/LaTeX surgery only. Input is abstracted behind a `NoteSource` seam (`FileSource` now, `OneNoteSource` later).

**Tech Stack:** Python 3.11+, FastMCP (`from fastmcp import FastMCP`, `@mcp.tool`, `mcp.run()`), PyMuPDF (`fitz`) for PDF→PNG, python-dateutil for date parsing, pytest for tests.

## Global Constraints

- Package import name: `scribe_tex`; repo/project name: `scribe-tex`.
- Server is **offline and deterministic**: no network calls, no API keys, no LLM calls in server code.
- **Write-only**: never compile LaTeX; never shell out to a TeX distribution.
- Notes root resolves from env `SCRIBE_TEX_NOTES_ROOT`, default `~/Desktop/College/Notes`.
- Each class date = `\section{<Month D, YYYY>}` + `\label{sec:<YYYY-MM-DD>}`, placed between `% >>> ENTRIES` and `% <<< ENTRIES` markers, kept in ascending date order.
- Duplicate policy default is `warn` (refuse + report); never silently overwrite.
- `placement.py` must be pure (no I/O) so it is exhaustively unit-testable.
- Follow TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit.

---

### Task 1: Project scaffold & packaging

**Files:**
- Create: `pyproject.toml`
- Create: `src/scribe_tex/__init__.py`
- Create: `tests/__init__.py`
- Create: `.gitignore`
- Create: `README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: an installable package `scribe_tex` with pytest runnable; `scribe_tex.__version__` = `"0.1.0"`.

- [ ] **Step 1: Write the failing test**

`tests/test_package.py`:
```python
def test_package_imports_and_has_version():
    import scribe_tex
    assert scribe_tex.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/scribe-tex && python -m pytest tests/test_package.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scribe_tex'`.

- [ ] **Step 3: Write minimal implementation**

`pyproject.toml`:
```toml
[project]
name = "scribe-tex"
version = "0.1.0"
description = "Convert handwritten note exports into per-course dated LaTeX documents."
requires-python = ">=3.11"
dependencies = [
    "fastmcp>=2.0",
    "pymupdf>=1.24",
    "python-dateutil>=2.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
scribe-tex = "scribe_tex.server:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

`src/scribe_tex/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/__init__.py`: (empty file)

`.gitignore`:
```
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
build/
dist/
.venv/
```

`README.md`:
```markdown
# scribe-tex

A FastMCP server that files agent-transcribed handwritten notes into per-course
LaTeX documents, one dated `\section` per class, in date order.

The calling agent (e.g. Claude Code) does the vision transcription; this server
does deterministic, offline LaTeX placement only — it never compiles LaTeX and
never makes a network call.

## Install

```bash
pip install -e ".[dev]"
```

## MCP tools

- `prepare_note(source="file", ref)` — render a note export to page PNGs and
  return a transcription brief + known courses.
- `resolve_placement(course_hint, date)` — map to a course document and report
  where the dated section will land (and whether that date already exists).
- `write_section(course, date, latex_body, on_duplicate="warn")` — scaffold the
  course if new and insert the section in date order.

## Configuration

- `SCRIBE_TEX_NOTES_ROOT` — parent folder holding one repo per course.
  Default: `~/Desktop/College/Notes`.
```

The `pythonpath = ["src"]` pytest setting lets tests import `scribe_tex` without an editable install; still document `pip install -e` for real use.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_package.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/Projects/scribe-tex
git add pyproject.toml src/scribe_tex/__init__.py tests/__init__.py tests/test_package.py .gitignore README.md
git commit -m "chore: scaffold scribe-tex package"
```

---

### Task 2: Config — notes root resolution

**Files:**
- Create: `src/scribe_tex/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `notes_root() -> pathlib.Path` — returns `Path` from env `SCRIBE_TEX_NOTES_ROOT` if set (expanduser), else `~/Desktop/College/Notes` expanded. Does NOT create the directory.

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from pathlib import Path
from scribe_tex.config import notes_root


def test_default_notes_root(monkeypatch):
    monkeypatch.delenv("SCRIBE_TEX_NOTES_ROOT", raising=False)
    assert notes_root() == (Path.home() / "Desktop" / "College" / "Notes")


def test_env_override_is_expanded(monkeypatch):
    monkeypatch.setenv("SCRIBE_TEX_NOTES_ROOT", "~/somewhere/notes")
    assert notes_root() == (Path.home() / "somewhere" / "notes")


def test_notes_root_does_not_create_dir(monkeypatch, tmp_path):
    target = tmp_path / "made_up"
    monkeypatch.setenv("SCRIBE_TEX_NOTES_ROOT", str(target))
    _ = notes_root()
    assert not target.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scribe_tex.config'`.

- [ ] **Step 3: Write minimal implementation**

`src/scribe_tex/config.py`:
```python
"""Configuration: resolve the notes root directory."""
import os
from pathlib import Path

DEFAULT_NOTES_ROOT = Path.home() / "Desktop" / "College" / "Notes"
ENV_VAR = "SCRIBE_TEX_NOTES_ROOT"


def notes_root() -> Path:
    """Return the parent folder that holds one repo per course.

    Reads env var SCRIBE_TEX_NOTES_ROOT (with ~ expansion) if set, else the
    default ~/Desktop/College/Notes. Never creates the directory.
    """
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override).expanduser()
    return DEFAULT_NOTES_ROOT
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/scribe_tex/config.py tests/test_config.py
git commit -m "feat: notes-root config resolution"
```

---

### Task 3: Preamble template & macro inventory

**Files:**
- Create: `src/scribe_tex/preamble.py`
- Test: `tests/test_preamble.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `PREAMBLE_BODY: str` — the LaTeX preamble (package loads + macros), with **no** subfiles wiring, and with two `str.format`-style placeholders `{footer_name}` and `{course_number}` in the fancy header.
  - `ALLOWED_MACROS: list[str]` — names of custom `\newcommand`s the agent may use (e.g. `\R`, `\prb`, `\e`, `\Dstroke`, `\kB`, `\pKa`, `\pH`, ...).
  - `ALLOWED_PACKAGES: list[str]` — package names loaded by the preamble.
  - `render_preamble(footer_name: str, course_number: str) -> str` — fills the placeholders.

- [ ] **Step 1: Write the failing test**

`tests/test_preamble.py`:
```python
from scribe_tex.preamble import (
    PREAMBLE_BODY,
    ALLOWED_MACROS,
    ALLOWED_PACKAGES,
    render_preamble,
)


def test_preamble_has_no_subfiles_wiring():
    # v1 uses standalone main.tex per course; subfiles machinery must be gone.
    assert "subfiles" not in PREAMBLE_BODY
    assert "subfix" not in PREAMBLE_BODY
    assert "addbibresource" not in PREAMBLE_BODY


def test_preamble_keeps_core_math_packages():
    for pkg in ("amsmath", "amssymb", "mathtools", "physics"):
        assert pkg in ALLOWED_PACKAGES


def test_allowed_macros_include_custom_commands():
    for macro in (r"\R", r"\prb", r"\e", r"\Dstroke", r"\pKa"):
        assert macro in ALLOWED_MACROS


def test_render_fills_placeholders():
    out = render_preamble(footer_name="Robles", course_number="MATH 257")
    assert "Robles" in out
    assert "MATH 257" in out
    assert "{footer_name}" not in out
    assert "{course_number}" not in out


def test_render_is_valid_when_no_stray_braces_break_format():
    # Ensures literal LaTeX braces were escaped so .format only sees our 2 fields.
    render_preamble(footer_name="X", course_number="Y")  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_preamble.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/scribe_tex/preamble.py`. Adapt the user's provided preamble: remove `\usepackage{subfiles}`, `\addbibresource{\subfix{...}}`, `\DefineBibliographyStrings`, and the `\graphicspath{{../ExtFiles/}}` external path; turn the fancy footer `Labalme` and header `3.942` into `{footer_name}` / `{course_number}`. Because the LaTeX contains many literal `{` `}`, store the body with all literal braces doubled (`{{`/`}}`) so `str.format` only substitutes our two named fields.

```python
r"""Canonical LaTeX preamble for a scribe-tex course document.

Adapted from the user's provided preamble: subfiles/bibresource wiring removed
so each course compiles as a standalone main.tex. The fancy header footer name
and course number are template placeholders.

Braces are doubled ({{ }}) so str.format substitutes ONLY {footer_name} and
{course_number}.
"""

# NOTE: every literal LaTeX brace below is doubled for str.format safety.
PREAMBLE_BODY = r"""\documentclass[11pt]{{article}}
\usepackage[margin=1in]{{geometry}}
\usepackage{{csquotes}}
\usepackage{{fancyhdr}}
\usepackage{{marginnote}}
\usepackage{{enumitem}}
\usepackage{{scrextend}}
\usepackage[bottom]{{footmisc}}
\usepackage{{siunitx}}
\usepackage{{tikz,graphicx}}
\usepackage{{float,subcaption}}
\usepackage{{booktabs,multirow}}
\usepackage{{amsmath,amssymb,amsthm}}
\usepackage{{bm,physics,mathtools,empheq}}
\usepackage[T1]{{fontenc}}
\usepackage{{mhchem}}
\usepackage[colorlinks,allcolors=black,urlcolor=cyan]{{hyperref}}

\MakeOuterQuote{{"}}

\fancypagestyle{{main}}{{
    \fancyhf{{}}
    \fancyhead[L]{{\leftmark}}
    \fancyhead[R]{{{course_number}}}
    \fancyfoot[R]{{{footer_name}\ \thepage}}
}}
\fancypagestyle{{plain}}{{
    \fancyhead{{}}
    \renewcommand{{\headrulewidth}}{{0pt}}
}}

\reversemarginpar

\setitemize[3]{{label={{\scriptsize$\blacksquare$}}}}

\deffootnotemark{{\textsuperscript{{\textup{{[}}\thefootnotemark\textup{{]}}}}}}
\deffootnote[1.8em]{{0em}}{{0em}}{{\textsuperscript{{\thefootnote}}}}

\sisetup{{range-phrase=-,range-units=single}}

\usetikzlibrary{{fpu,shapes,angles,decorations.markings,decorations.pathmorphing}}
\colorlet{{rex}}{{red!80!black!90!orange!80}}
\colorlet{{blx}}{{blue!90!green!80}}
\definecolor{{DeepCerulean}}{{HTML}}{{006fb3}}
\colorlet{{grx}}{{green!50!black}}
\colorlet{{pux}}{{red!50!blue}}

\newcommand{{\kB}}{{k_\text{{B}}}}
\newcommand{{\lB}}{{\ell_\text{{B}}}}
\newcommand{{\Tg}}{{T_\text{{g}}}}
\newcommand{{\Tm}}{{T_\text{{m}}}}
\newcommand{{\Tc}}{{T_\text{{c}}}}
\newcommand{{\Mn}}{{M_\text{{n}}}}
\newcommand{{\Mw}}{{M_\text{{w}}}}
\newcommand{{\R}}{{\mathbb{{R}}}}
\newcommand{{\pKa}}{{\text{{p}}K_\text{{a}}}}
\newcommand{{\pH}}{{\text{{pH}}}}
\newcommand{{\e}}[1][]{{\text{{e}}^{{#1}}}}
\newcommand{{\prb}}[1]{{\left\langle{{#1}}\right\rangle}}
\newcommand{{\Dstroke}}{{\tikz{{
    \node[inner sep=0pt]{{$D$}};
    \draw (-0.1,0) -- ++(0.12,0);
}}}}
"""

ALLOWED_PACKAGES = [
    "geometry", "csquotes", "fancyhdr", "marginnote", "enumitem", "scrextend",
    "footmisc", "siunitx", "tikz", "graphicx", "float", "subcaption",
    "booktabs", "multirow", "amsmath", "amssymb", "amsthm", "bm", "physics",
    "mathtools", "empheq", "fontenc", "mhchem", "hyperref",
]

ALLOWED_MACROS = [
    r"\kB", r"\lB", r"\Tg", r"\Tm", r"\Tc", r"\Mn", r"\Mw", r"\R", r"\pKa",
    r"\pH", r"\e", r"\prb", r"\Dstroke",
]


def render_preamble(footer_name: str, course_number: str) -> str:
    """Fill the footer name and course number into the preamble template."""
    return PREAMBLE_BODY.format(footer_name=footer_name, course_number=course_number)
```

Note: `\Dstroke` was simplified (dropped the fragile `\Dstroke` variant with a raw `D`) to keep the macro set clean; the `\prb`, `\e`, `\R`, `\pKa` etc. are preserved verbatim.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_preamble.py -v`
Expected: PASS (5 tests). If `render_preamble` raises `KeyError`/`IndexError`, a literal brace was left un-doubled — fix that brace.

- [ ] **Step 5: Commit**

```bash
git add src/scribe_tex/preamble.py tests/test_preamble.py
git commit -m "feat: standalone preamble template with macro inventory"
```

---

### Task 4: Date parsing & normalization

**Files:**
- Create: `src/scribe_tex/classify.py`
- Test: `tests/test_classify_dates.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `parse_date(raw: str) -> str | None` — returns ISO `YYYY-MM-DD`, or `None` if unparseable/ambiguous. Accepts `"2025-10-03"`, `"Oct 3 2025"`, `"October 3, 2025"`, `"10/3/2025"`, `"10/3/25"`. Returns `None` for a bare `"3/4"` (no year) and for gibberish.
  - `display_date(iso: str) -> str` — `"2025-10-03"` → `"October 3, 2025"`.

- [ ] **Step 1: Write the failing test**

`tests/test_classify_dates.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_classify_dates.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/scribe_tex/classify.py`:
```python
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
    # Reject slash dates with no year, e.g. "3/4".
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_classify_dates.py -v`
Expected: PASS. If `"10/3/25"` fails, confirm dateutil expands 2-digit years; if it maps to 1925, add a pivot: after parsing, if `dt.year < 100` add 2000 — but dateutil's default pivots to 2000s already, so this should pass as written.

- [ ] **Step 5: Commit**

```bash
git add src/scribe_tex/classify.py tests/test_classify_dates.py
git commit -m "feat: date parsing and display normalization"
```

---

### Task 5: Course slug & fuzzy matching

**Files:**
- Modify: `src/scribe_tex/classify.py`
- Test: `tests/test_classify_courses.py`

**Interfaces:**
- Consumes: nothing new.
- Produces (added to `classify.py`):
  - `course_slug(name: str) -> str` — folder-safe slug: `"MATH 257 Linear Algebra"` → `"MATH-257-Linear-Algebra"` (collapse whitespace to single hyphens, strip characters outside `[A-Za-z0-9-]`, no leading/trailing hyphens).
  - `match_course(hint: str, known: list[str]) -> tuple[str | None, str]` — returns `(matched_course_name_or_None, confidence)` where confidence ∈ `{"high", "low", "none"}`. High = case-insensitive substring match of hint tokens against exactly one known course; low = a weak/partial single match; none = no match (course is new).

- [ ] **Step 1: Write the failing test**

`tests/test_classify_courses.py`:
```python
from scribe_tex.classify import course_slug, match_course

KNOWN = ["MATH 257 Linear Algebra", "CHEM 20100 Inorganic Chemistry I"]


def test_course_slug():
    assert course_slug("MATH 257 Linear Algebra") == "MATH-257-Linear-Algebra"
    assert course_slug("  Weird!! name??  ") == "Weird-name"


def test_high_confidence_exact_token():
    course, conf = match_course("linear algebra", KNOWN)
    assert course == "MATH 257 Linear Algebra"
    assert conf == "high"


def test_high_confidence_by_number():
    course, conf = match_course("math 257", KNOWN)
    assert course == "MATH 257 Linear Algebra"
    assert conf == "high"


def test_no_match_is_new():
    course, conf = match_course("Organic Chemistry", KNOWN)
    assert course is None
    assert conf == "none"


def test_ambiguous_is_low():
    known = ["MATH 257 Linear Algebra", "MATH 258 Linear Algebra II"]
    course, conf = match_course("linear algebra", known)
    assert conf == "low"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_classify_courses.py -v`
Expected: FAIL — `ImportError: cannot import name 'course_slug'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/scribe_tex/classify.py`:
```python
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
        return winners[0], confidence
    return None, "low"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_classify_courses.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/scribe_tex/classify.py tests/test_classify_courses.py
git commit -m "feat: course slug and fuzzy hint matching"
```

---

### Task 6: Placement engine (pure)

**Files:**
- Create: `src/scribe_tex/placement.py`
- Test: `tests/test_placement.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces:
  - `ENTRIES_START = "% >>> ENTRIES"`, `ENTRIES_END = "% <<< ENTRIES"`.
  - `existing_dates(main_tex: str) -> list[str]` — ISO dates from `\label{sec:YYYY-MM-DD}` in document order.
  - `section_block(date_iso: str, display: str, body: str) -> str` — the full `\section{...}\label{...}` block with begin/end body markers.
  - `plan_insertion(main_tex: str, date_iso: str) -> dict` — returns `{"duplicate": bool, "after_date": str | None, "insert_index": int}` where `insert_index` is the character offset in `main_tex` at which a new block should be inserted to keep dates ascending.

- [ ] **Step 1: Write the failing test**

`tests/test_placement.py`:
```python
from scribe_tex.placement import (
    ENTRIES_START, ENTRIES_END, existing_dates, section_block, plan_insertion,
)

EMPTY = f"""\\begin{{document}}
{ENTRIES_START}
{ENTRIES_END}
\\end{{document}}
"""


def _doc_with(dates):
    blocks = "\n".join(
        section_block(d, d, f"body {d}") for d in dates
    )
    return f"\\begin{{document}}\n{ENTRIES_START}\n{blocks}\n{ENTRIES_END}\n\\end{{document}}\n"


def test_section_block_has_label_and_markers():
    blk = section_block("2025-10-03", "October 3, 2025", "hi")
    assert r"\section{October 3, 2025}" in blk
    assert r"\label{sec:2025-10-03}" in blk
    assert "begin transcribed body" in blk
    assert "end transcribed body" in blk
    assert "hi" in blk


def test_existing_dates_in_order():
    doc = _doc_with(["2025-09-28", "2025-10-03"])
    assert existing_dates(doc) == ["2025-09-28", "2025-10-03"]


def test_first_insertion_into_empty():
    p = plan_insertion(EMPTY, "2025-10-03")
    assert p["duplicate"] is False
    assert p["after_date"] is None
    # insert_index points just after the ENTRIES_START line
    assert EMPTY[:p["insert_index"]].rstrip().endswith(ENTRIES_START)


def test_insert_between_keeps_order():
    doc = _doc_with(["2025-09-28", "2025-10-10"])
    p = plan_insertion(doc, "2025-10-03")
    assert p["duplicate"] is False
    assert p["after_date"] == "2025-09-28"


def test_insert_before_all():
    doc = _doc_with(["2025-10-03"])
    p = plan_insertion(doc, "2025-09-01")
    assert p["after_date"] is None


def test_insert_after_all():
    doc = _doc_with(["2025-09-01", "2025-10-03"])
    p = plan_insertion(doc, "2025-12-01")
    assert p["after_date"] == "2025-10-03"


def test_duplicate_detected():
    doc = _doc_with(["2025-10-03"])
    p = plan_insertion(doc, "2025-10-03")
    assert p["duplicate"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_placement.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/scribe_tex/placement.py`:
```python
"""Pure LaTeX placement logic: enumerate dates, build blocks, plan insertion.

No I/O. All functions operate on the main.tex text as a string.
"""
from __future__ import annotations
import re

ENTRIES_START = "% >>> ENTRIES"
ENTRIES_END = "% <<< ENTRIES"
_LABEL_RE = re.compile(r"\\label\{sec:(\d{4}-\d{2}-\d{2})\}")


def existing_dates(main_tex: str) -> list[str]:
    """ISO dates from \\label{sec:...} anchors, in document order."""
    return _LABEL_RE.findall(main_tex)


def section_block(date_iso: str, display: str, body: str) -> str:
    """Full section block for one class date."""
    return (
        f"\\section{{{display}}}\n"
        f"\\label{{sec:{date_iso}}}\n"
        f"% --- begin transcribed body ---\n"
        f"{body}\n"
        f"% --- end transcribed body ---\n"
    )


def plan_insertion(main_tex: str, date_iso: str) -> dict:
    """Decide where a new dated block should go to keep dates ascending.

    Returns {"duplicate", "after_date", "insert_index"}.
    """
    dates = existing_dates(main_tex)
    if date_iso in dates:
        return {"duplicate": True, "after_date": None, "insert_index": -1}

    earlier = [d for d in dates if d < date_iso]
    after_date = earlier[-1] if earlier else None

    if after_date is None:
        # Insert immediately after the ENTRIES_START marker line.
        idx = main_tex.index(ENTRIES_START) + len(ENTRIES_START)
        # advance past the newline
        if idx < len(main_tex) and main_tex[idx] == "\n":
            idx += 1
        return {"duplicate": False, "after_date": None, "insert_index": idx}

    # Insert after the block whose label is `after_date`: find that label,
    # then the position right after its end-of-body marker (next end marker
    # after the label), else after the label line.
    label = f"\\label{{sec:{after_date}}}"
    label_pos = main_tex.index(label)
    end_marker = "% --- end transcribed body ---"
    end_pos = main_tex.find(end_marker, label_pos)
    if end_pos == -1:
        cut = main_tex.index("\n", label_pos) + 1
    else:
        cut = main_tex.index("\n", end_pos) + 1
    return {"duplicate": False, "after_date": after_date, "insert_index": cut}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_placement.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/scribe_tex/placement.py tests/test_placement.py
git commit -m "feat: pure placement engine (dates, blocks, insertion planning)"
```

---

### Task 7: Scaffold a new course document

**Files:**
- Create: `src/scribe_tex/scaffold.py`
- Test: `tests/test_scaffold.py`

**Interfaces:**
- Consumes: `render_preamble` (Task 3); `ENTRIES_START`/`ENTRIES_END` (Task 6); `course_slug` (Task 5).
- Produces:
  - `DEFAULT_FOOTER_NAME = "Robles"`.
  - `build_main_tex(course_name: str, course_number: str, footer_name: str = DEFAULT_FOOTER_NAME) -> str` — full standalone document string: preamble + `\begin{document}` + title block + `\tableofcontents` under a "Topics" rename + empty ENTRIES region + `\end{document}`.
  - `scaffold_course(root: Path, course_name: str, course_number: str, footer_name: str = DEFAULT_FOOTER_NAME) -> Path` — creates `root/<slug>/main.tex` (making dirs), returns the `main.tex` path. Refuses (raises `FileExistsError`) if `main.tex` already exists.

- [ ] **Step 1: Write the failing test**

`tests/test_scaffold.py`:
```python
import pytest
from scribe_tex.scaffold import build_main_tex, scaffold_course, DEFAULT_FOOTER_NAME
from scribe_tex.placement import ENTRIES_START, ENTRIES_END


def test_build_main_tex_shape():
    doc = build_main_tex("MATH 257 Linear Algebra", "MATH 257")
    assert doc.count(r"\begin{document}") == 1
    assert doc.count(r"\end{document}") == 1
    assert ENTRIES_START in doc and ENTRIES_END in doc
    assert doc.index(ENTRIES_START) < doc.index(ENTRIES_END)
    assert "Topics" in doc                 # renamed contents heading
    assert "MATH 257 Linear Algebra" in doc  # title
    assert DEFAULT_FOOTER_NAME in doc
    # entries region starts empty
    region = doc[doc.index(ENTRIES_START) + len(ENTRIES_START):doc.index(ENTRIES_END)]
    assert region.strip() == ""


def test_scaffold_creates_file(tmp_path):
    p = scaffold_course(tmp_path, "MATH 257 Linear Algebra", "MATH 257")
    assert p.exists()
    assert p.parent.name == "MATH-257-Linear-Algebra"
    assert p.name == "main.tex"


def test_scaffold_refuses_overwrite(tmp_path):
    scaffold_course(tmp_path, "MATH 257 Linear Algebra", "MATH 257")
    with pytest.raises(FileExistsError):
        scaffold_course(tmp_path, "MATH 257 Linear Algebra", "MATH 257")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scaffold.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/scribe_tex/scaffold.py`:
```python
"""Create a new per-course LaTeX document."""
from __future__ import annotations
from pathlib import Path

from .preamble import render_preamble
from .placement import ENTRIES_START, ENTRIES_END
from .classify import course_slug

DEFAULT_FOOTER_NAME = "Robles"


def build_main_tex(course_name: str, course_number: str,
                   footer_name: str = DEFAULT_FOOTER_NAME) -> str:
    preamble = render_preamble(footer_name=footer_name, course_number=course_number)
    return (
        preamble
        + "\n\\begin{document}\n"
        + "\\pagestyle{main}\n"
        + f"\\title{{{course_name} Notes}}\n"
        + f"\\author{{{footer_name}}}\n"
        + "\\date{}\n"
        + "\\maketitle\n\n"
        + "\\renewcommand{\\contentsname}{Topics}\n"
        + "\\tableofcontents\n"
        + "\\newpage\n\n"
        + f"{ENTRIES_START}\n{ENTRIES_END}\n"
        + "\\end{document}\n"
    )


def scaffold_course(root: Path, course_name: str, course_number: str,
                    footer_name: str = DEFAULT_FOOTER_NAME) -> Path:
    course_dir = root / course_slug(course_name)
    main_tex = course_dir / "main.tex"
    if main_tex.exists():
        raise FileExistsError(main_tex)
    course_dir.mkdir(parents=True, exist_ok=True)
    main_tex.write_text(build_main_tex(course_name, course_number, footer_name),
                        encoding="utf-8")
    return main_tex
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scaffold.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/scribe_tex/scaffold.py tests/test_scaffold.py
git commit -m "feat: scaffold a new per-course document"
```

---

### Task 8: Writer — insert a section into main.tex

**Files:**
- Create: `src/scribe_tex/writer.py`
- Test: `tests/test_writer.py`

**Interfaces:**
- Consumes: `plan_insertion`, `section_block`, `existing_dates`, `ENTRIES_START`/`ENTRIES_END` (Task 6); `display_date` (Task 4).
- Produces:
  - `class DuplicateDateError(Exception)` (carries `.date_iso`).
  - `class MalformedDocumentError(Exception)`.
  - `insert_section(main_tex: str, date_iso: str, body: str, on_duplicate: str = "warn") -> tuple[str, str]` — returns `(new_main_tex, diff_summary)`. Raises `MalformedDocumentError` if markers are missing. On duplicate: `warn` → raise `DuplicateDateError`; `replace` → swap that date's block; `append` → add a second block right after the existing same-date block.

- [ ] **Step 1: Write the failing test**

`tests/test_writer.py`:
```python
import pytest
from scribe_tex.writer import (
    insert_section, DuplicateDateError, MalformedDocumentError,
)
from scribe_tex.placement import ENTRIES_START, ENTRIES_END, existing_dates

BASE = f"\\begin{{document}}\n{ENTRIES_START}\n{ENTRIES_END}\n\\end{{document}}\n"


def test_insert_first_section():
    out, summary = insert_section(BASE, "2025-10-03", "hello")
    assert existing_dates(out) == ["2025-10-03"]
    assert r"\section{October 3, 2025}" in out
    assert "hello" in out
    assert "inserted" in summary.lower()


def test_insert_keeps_date_order():
    out, _ = insert_section(BASE, "2025-10-10", "b")
    out, _ = insert_section(out, "2025-09-28", "a")
    out, _ = insert_section(out, "2025-10-03", "c")
    assert existing_dates(out) == ["2025-09-28", "2025-10-03", "2025-10-10"]


def test_duplicate_warn_raises():
    out, _ = insert_section(BASE, "2025-10-03", "x")
    with pytest.raises(DuplicateDateError):
        insert_section(out, "2025-10-03", "y", on_duplicate="warn")


def test_duplicate_replace_swaps_body():
    out, _ = insert_section(BASE, "2025-10-03", "OLD")
    out, _ = insert_section(out, "2025-10-03", "NEW", on_duplicate="replace")
    assert "NEW" in out and "OLD" not in out
    assert existing_dates(out) == ["2025-10-03"]


def test_duplicate_append_adds_second():
    out, _ = insert_section(BASE, "2025-10-03", "first")
    out, _ = insert_section(out, "2025-10-03", "second", on_duplicate="append")
    assert existing_dates(out) == ["2025-10-03", "2025-10-03"]
    assert "first" in out and "second" in out


def test_malformed_missing_markers_raises():
    with pytest.raises(MalformedDocumentError):
        insert_section("\\begin{document}\n\\end{document}\n", "2025-10-03", "x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_writer.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/scribe_tex/writer.py`:
```python
"""Apply a section insertion to a course main.tex, returning new text + summary."""
from __future__ import annotations

from .placement import (
    ENTRIES_START, ENTRIES_END, plan_insertion, section_block, existing_dates,
)
from .classify import display_date


class DuplicateDateError(Exception):
    def __init__(self, date_iso: str):
        super().__init__(f"section for {date_iso} already exists")
        self.date_iso = date_iso


class MalformedDocumentError(Exception):
    pass


def _require_markers(main_tex: str) -> None:
    if ENTRIES_START not in main_tex or ENTRIES_END not in main_tex:
        raise MalformedDocumentError("ENTRIES markers not found")


def _block(date_iso: str, body: str) -> str:
    return section_block(date_iso, display_date(date_iso), body)


def _replace_block(main_tex: str, date_iso: str, body: str) -> str:
    label = f"\\label{{sec:{date_iso}}}"
    label_pos = main_tex.index(label)
    sec_pos = main_tex.rindex("\\section{", 0, label_pos)
    end_marker = "% --- end transcribed body ---"
    end_pos = main_tex.index(end_marker, label_pos)
    block_end = main_tex.index("\n", end_pos) + 1
    return main_tex[:sec_pos] + _block(date_iso, body) + main_tex[block_end:]


def insert_section(main_tex: str, date_iso: str, body: str,
                   on_duplicate: str = "warn") -> tuple[str, str]:
    _require_markers(main_tex)
    plan = plan_insertion(main_tex, date_iso)

    if plan["duplicate"]:
        if on_duplicate == "warn":
            raise DuplicateDateError(date_iso)
        if on_duplicate == "replace":
            new = _replace_block(main_tex, date_iso, body)
            return new, f"replaced section dated {date_iso}"
        if on_duplicate == "append":
            # Insert a second block right after the existing same-date block.
            label = f"\\label{{sec:{date_iso}}}"
            label_pos = main_tex.index(label)
            end_marker = "% --- end transcribed body ---"
            end_pos = main_tex.index(end_marker, label_pos)
            cut = main_tex.index("\n", end_pos) + 1
            new = main_tex[:cut] + _block(date_iso, body) + main_tex[cut:]
            return new, f"appended second section dated {date_iso}"
        raise ValueError(f"unknown on_duplicate: {on_duplicate}")

    idx = plan["insert_index"]
    new = main_tex[:idx] + _block(date_iso, body) + main_tex[idx:]
    where = "at start" if plan["after_date"] is None else f"after {plan['after_date']}"
    return new, f"inserted section dated {date_iso} ({where})"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_writer.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/scribe_tex/writer.py tests/test_writer.py
git commit -m "feat: section writer with duplicate policies"
```

---

### Task 9: NoteSource seam + FileSource

**Files:**
- Create: `src/scribe_tex/sources/__init__.py`
- Create: `src/scribe_tex/sources/base.py`
- Create: `src/scribe_tex/sources/file_source.py`
- Create: `src/scribe_tex/sources/onenote_source.py`
- Test: `tests/test_file_source.py`

**Interfaces:**
- Consumes: nothing internal (uses `fitz` from PyMuPDF).
- Produces:
  - `base.py`: `class NoteSource(Protocol): def fetch_pages(self, ref: str) -> list[Path]: ...`; `register(name, factory)`, `get_source(name) -> NoteSource`.
  - `file_source.py`: `class FileSource` — `fetch_pages(ref)` renders a PDF to one PNG per page in a temp dir (via `fitz`), or passes through a single image path (`.png/.jpg/.jpeg`) as a one-element list. Raises `FileNotFoundError` for missing paths, `ValueError` for unsupported extensions. Registered under `"file"`.
  - `onenote_source.py`: `class OneNoteSource` — `fetch_pages` raises `NotImplementedError` with a docstring describing the future Graph `/preview` + `data-fullres-src` path. Registered under `"onenote"`.

- [ ] **Step 1: Write the failing test**

`tests/test_file_source.py`:
```python
import pytest
from pathlib import Path
from scribe_tex.sources.base import get_source
from scribe_tex.sources.file_source import FileSource


def _make_pdf(path: Path, pages: int) -> None:
    import fitz
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()


def test_registered_file_source():
    assert isinstance(get_source("file"), FileSource)


def test_pdf_renders_one_png_per_page(tmp_path):
    pdf = tmp_path / "note.pdf"
    _make_pdf(pdf, 3)
    pngs = FileSource().fetch_pages(str(pdf))
    assert len(pngs) == 3
    assert all(p.suffix == ".png" and p.exists() for p in pngs)


def test_single_image_passthrough(tmp_path):
    img = tmp_path / "note.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")  # header only; path handling under test
    out = FileSource().fetch_pages(str(img))
    assert out == [img]


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        FileSource().fetch_pages(str(tmp_path / "nope.pdf"))


def test_unsupported_extension_raises(tmp_path):
    bad = tmp_path / "note.txt"
    bad.write_text("x")
    with pytest.raises(ValueError):
        FileSource().fetch_pages(str(bad))


def test_onenote_source_not_implemented():
    from scribe_tex.sources.onenote_source import OneNoteSource
    with pytest.raises(NotImplementedError):
        OneNoteSource().fetch_pages("anything")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_file_source.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/scribe_tex/sources/__init__.py`:
```python
from . import file_source, onenote_source  # noqa: F401  (register on import)
```

`src/scribe_tex/sources/base.py`:
```python
"""NoteSource protocol and registry."""
from __future__ import annotations
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

@runtime_checkable
class NoteSource(Protocol):
    def fetch_pages(self, ref: str) -> list[Path]:
        """Return page images (PNG paths) for the given source reference."""
        ...

_REGISTRY: dict[str, Callable[[], NoteSource]] = {}


def register(name: str, factory: Callable[[], NoteSource]) -> None:
    _REGISTRY[name] = factory


def get_source(name: str) -> NoteSource:
    if name not in _REGISTRY:
        raise ValueError(f"unknown note source: {name!r}")
    return _REGISTRY[name]()
```

`src/scribe_tex/sources/file_source.py`:
```python
"""FileSource: render a local PDF/image note export to page PNGs."""
from __future__ import annotations
import tempfile
from pathlib import Path

from .base import NoteSource, register

_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


class FileSource:
    def fetch_pages(self, ref: str) -> list[Path]:
        path = Path(ref).expanduser()
        if not path.exists():
            raise FileNotFoundError(path)
        ext = path.suffix.lower()
        if ext in _IMAGE_EXTS:
            return [path]
        if ext != ".pdf":
            raise ValueError(f"unsupported note file type: {ext}")
        import fitz  # PyMuPDF
        out_dir = Path(tempfile.mkdtemp(prefix="scribe_tex_"))
        doc = fitz.open(str(path))
        pages: list[Path] = []
        try:
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=200)
                out = out_dir / f"p{i + 1}.png"
                pix.save(str(out))
                pages.append(out)
        finally:
            doc.close()
        return pages


register("file", FileSource)
```

`src/scribe_tex/sources/onenote_source.py`:
```python
"""OneNoteSource: future Graph-backed page-image fetcher (not implemented).

The Microsoft Graph OneNote API cannot return handwritten ink as text or
strokes, but CAN return page images via the page /preview endpoint and the
img data-fullres-src resource endpoint
(GET /me/onenote/resources/{id}/$value). A future implementation would
authenticate (delegated OAuth2, scope Notes.Read), resolve a page by
course/date, download those PNGs, and return them here so the rest of the
pipeline is unchanged.
"""
from __future__ import annotations
from pathlib import Path

from .base import register


class OneNoteSource:
    def fetch_pages(self, ref: str) -> list[Path]:
        raise NotImplementedError(
            "OneNoteSource is a future seam; use source='file' for now."
        )


register("onenote", OneNoteSource)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_file_source.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/scribe_tex/sources tests/test_file_source.py
git commit -m "feat: NoteSource seam with FileSource and OneNote stub"
```

---

### Task 10: Transcription brief builder

**Files:**
- Create: `src/scribe_tex/transcription_brief.py`
- Test: `tests/test_transcription_brief.py`

**Interfaces:**
- Consumes: `ALLOWED_PACKAGES`, `ALLOWED_MACROS` (Task 3).
- Produces: `build_brief() -> str` — a plain-text instruction string listing allowed packages + macros, house-style rules (LaTeX body only — no preamble, no `\begin{document}`; use `$...$`/`align`; `\subsection` for topics), and the extraction request (course hint + class date).

- [ ] **Step 1: Write the failing test**

`tests/test_transcription_brief.py`:
```python
from scribe_tex.transcription_brief import build_brief
from scribe_tex.preamble import ALLOWED_MACROS


def test_brief_lists_macros_and_rules():
    brief = build_brief()
    for macro in ALLOWED_MACROS:
        assert macro in brief
    assert "course" in brief.lower()
    assert "date" in brief.lower()
    # must instruct body-only (no preamble)
    assert "begin{document}" in brief  # referenced in a "do NOT include" rule
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_transcription_brief.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/scribe_tex/transcription_brief.py`:
```python
"""Build the transcription brief handed to the calling agent."""
from __future__ import annotations

from .preamble import ALLOWED_PACKAGES, ALLOWED_MACROS


def build_brief() -> str:
    packages = ", ".join(ALLOWED_PACKAGES)
    macros = ", ".join(ALLOWED_MACROS)
    return (
        "Transcribe the handwritten note page images into LaTeX.\n"
        "\n"
        "OUTPUT RULES:\n"
        "- Produce the SECTION BODY ONLY. Do NOT include a preamble, "
        "\\documentclass, or \\begin{document}/\\end{document}.\n"
        "- Do NOT write the \\section or \\label line; the server adds those.\n"
        "- Use $...$ for inline math and align/equation for display math.\n"
        "- Use \\subsection{...} for topics within the class.\n"
        f"- You MAY rely on these already-loaded packages: {packages}.\n"
        f"- You MAY use these predefined macros: {macros}.\n"
        "\n"
        "ALSO EXTRACT (report separately, not inside the LaTeX):\n"
        "- course: the course name/number hint (from a header or the content).\n"
        "- date: the class date (look for a written date header).\n"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_transcription_brief.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scribe_tex/transcription_brief.py tests/test_transcription_brief.py
git commit -m "feat: transcription brief builder"
```

---

### Task 11: Discover known courses

**Files:**
- Create: `src/scribe_tex/discovery.py`
- Test: `tests/test_discovery.py`

**Interfaces:**
- Consumes: nothing internal.
- Produces: `known_courses(root: Path) -> list[str]` — for each immediate subdirectory of `root` that contains a `main.tex`, return a display name derived by replacing hyphens with spaces in the folder slug. Returns `[]` if `root` does not exist. Sorted.

- [ ] **Step 1: Write the failing test**

`tests/test_discovery.py`:
```python
from scribe_tex.discovery import known_courses


def test_empty_when_root_missing(tmp_path):
    assert known_courses(tmp_path / "nope") == []


def test_lists_courses_with_main_tex(tmp_path):
    (tmp_path / "MATH-257-Linear-Algebra").mkdir()
    (tmp_path / "MATH-257-Linear-Algebra" / "main.tex").write_text("x")
    (tmp_path / "CHEM-20100-Inorganic").mkdir()
    (tmp_path / "CHEM-20100-Inorganic" / "main.tex").write_text("x")
    (tmp_path / "not-a-course").mkdir()  # no main.tex -> excluded
    assert known_courses(tmp_path) == [
        "CHEM 20100 Inorganic",
        "MATH 257 Linear Algebra",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_discovery.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/scribe_tex/discovery.py`:
```python
"""Discover existing course documents under the notes root."""
from __future__ import annotations
from pathlib import Path


def known_courses(root: Path) -> list[str]:
    if not root.exists():
        return []
    names = []
    for child in root.iterdir():
        if child.is_dir() and (child / "main.tex").exists():
            names.append(child.name.replace("-", " "))
    return sorted(names)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_discovery.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scribe_tex/discovery.py tests/test_discovery.py
git commit -m "feat: discover known courses under notes root"
```

---

### Task 12: FastMCP server — wire the three tools

**Files:**
- Create: `src/scribe_tex/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: all prior modules.
- Produces (module-level functions, wrapped as `@mcp.tool`, but each also importable/callable directly for testing):
  - `prepare_note(source: str = "file", ref: str = "") -> dict`
  - `resolve_placement(course_hint: str, date: str) -> dict`
  - `write_section(course: str, date: str, latex_body: str, on_duplicate: str = "warn") -> dict`
  - `main()` — calls `mcp.run()`.

  Implement the logic in plain helper functions (`_prepare_note`, `_resolve_placement`, `_write_section`) so tests call those directly without the MCP layer; the `@mcp.tool` functions just delegate.

- [ ] **Step 1: Write the failing test**

`tests/test_server.py`:
```python
import pytest
from scribe_tex import server
from scribe_tex.placement import existing_dates


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBE_TEX_NOTES_ROOT", str(tmp_path))
    return tmp_path


def test_resolve_new_course(root):
    r = server._resolve_placement("Organic Chemistry", "Oct 3 2025")
    assert r["course_status"] == "new"
    assert r["date_iso"] == "2025-10-03"
    assert r["date_display"] == "October 3, 2025"
    assert r["duplicate"] is False


def test_resolve_bad_date(root):
    r = server._resolve_placement("Whatever", "someday")
    assert r["match_confidence"] == "low"
    assert r["date_iso"] is None


def test_write_scaffolds_and_inserts(root):
    r = server._write_section("MATH 257 Linear Algebra", "2025-10-03", "hello")
    assert r["written"] is True
    assert r["compiled"] is False
    main_tex = (root / "MATH-257-Linear-Algebra" / "main.tex").read_text()
    assert existing_dates(main_tex) == ["2025-10-03"]
    assert "hello" in main_tex


def test_write_then_resolve_sees_existing(root):
    server._write_section("MATH 257 Linear Algebra", "2025-10-03", "x")
    r = server._resolve_placement("linear algebra", "2025-10-10")
    assert r["course_status"] == "existing"
    assert r["course"] == "MATH 257 Linear Algebra"
    assert r["insert_position"] == "after section dated 2025-10-03"


def test_write_duplicate_warns(root):
    server._write_section("MATH 257 Linear Algebra", "2025-10-03", "x")
    r = server._write_section("MATH 257 Linear Algebra", "2025-10-03", "y")
    assert r["written"] is False
    assert "duplicate" in r["error"].lower()


def test_prepare_note_reports_root_and_courses(root):
    server._write_section("MATH 257 Linear Algebra", "2025-10-03", "x")
    # use a tiny generated PDF via FileSource path
    import fitz
    pdf = root / "note.pdf"
    d = fitz.open(); d.new_page(); d.save(str(pdf)); d.close()
    r = server._prepare_note("file", str(pdf))
    assert len(r["page_images"]) == 1
    assert r["notes_root"] == str(root)
    assert "MATH 257 Linear Algebra" in r["known_courses"]
    assert "course" in r["brief"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_server.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`src/scribe_tex/server.py`:
```python
"""FastMCP server: prepare_note, resolve_placement, write_section."""
from __future__ import annotations
from pathlib import Path

from fastmcp import FastMCP

from .config import notes_root
from .classify import parse_date, display_date, match_course, course_slug
from .discovery import known_courses
from .transcription_brief import build_brief
from .sources.base import get_source
from .scaffold import scaffold_course
from .writer import insert_section, DuplicateDateError, MalformedDocumentError
from .placement import plan_insertion

mcp = FastMCP("scribe-tex")


def _prepare_note(source: str = "file", ref: str = "") -> dict:
    try:
        pages = get_source(source).fetch_pages(ref)
    except (FileNotFoundError, ValueError, NotImplementedError) as e:
        return {"error": str(e), "page_images": []}
    root = notes_root()
    return {
        "page_images": [str(p) for p in pages],
        "brief": build_brief(),
        "notes_root": str(root),
        "known_courses": known_courses(root),
    }


def _resolve_placement(course_hint: str, date: str) -> dict:
    root = notes_root()
    known = known_courses(root)
    date_iso = parse_date(date)
    matched, confidence = match_course(course_hint, known)

    if matched is not None:
        course = matched
        status = "existing"
    else:
        course = course_hint
        status = "new"
        # a new course is a confident placement decision only if the date parsed
        confidence = "high" if date_iso else "low"

    slug = course_slug(course)
    target = root / slug / "main.tex"

    duplicate = False
    insert_position = "start (first section)"
    if date_iso and status == "existing" and target.exists():
        plan = plan_insertion(target.read_text(encoding="utf-8"), date_iso)
        duplicate = plan["duplicate"]
        if plan["after_date"]:
            insert_position = f"after section dated {plan['after_date']}"

    if not date_iso:
        confidence = "low"

    return {
        "course": course,
        "course_status": status,
        "target_path": str(target),
        "date_iso": date_iso,
        "date_display": display_date(date_iso) if date_iso else None,
        "insert_position": insert_position,
        "duplicate": duplicate,
        "match_confidence": confidence,
    }


def _write_section(course: str, date: str, latex_body: str,
                   on_duplicate: str = "warn") -> dict:
    root = notes_root()
    date_iso = parse_date(date)
    if not date_iso:
        return {"written": False, "error": f"unparseable date: {date!r}"}

    slug = course_slug(course)
    target = root / slug / "main.tex"
    if not target.exists():
        # infer a course number token (first token containing a digit) for the header
        number = next((t for t in course.split() if any(c.isdigit() for c in t)), course)
        scaffold_course(root, course, number)

    try:
        new_text, summary = insert_section(
            target.read_text(encoding="utf-8"), date_iso, latex_body, on_duplicate
        )
    except DuplicateDateError as e:
        return {"written": False,
                "error": f"duplicate date {e.date_iso}; choose on_duplicate="
                         f"'replace' or 'append', or skip."}
    except MalformedDocumentError as e:
        return {"written": False, "error": f"malformed document: {e}"}

    target.write_text(new_text, encoding="utf-8")
    return {"written": True, "target_path": str(target),
            "diff_summary": summary, "compiled": False}


@mcp.tool
def prepare_note(source: str = "file", ref: str = "") -> dict:
    """Render a note export to page PNGs and return a transcription brief."""
    return _prepare_note(source, ref)


@mcp.tool
def resolve_placement(course_hint: str, date: str) -> dict:
    """Map a note to a course document and report where its dated section lands."""
    return _resolve_placement(course_hint, date)


@mcp.tool
def write_section(course: str, date: str, latex_body: str,
                  on_duplicate: str = "warn") -> dict:
    """Scaffold the course if new and insert the dated section in date order."""
    return _write_section(course, date, latex_body, on_duplicate)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_server.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/scribe_tex/server.py tests/test_server.py
git commit -m "feat: FastMCP server wiring the three tools"
```

---

### Task 13: Full suite green + MCP config docs

**Files:**
- Modify: `README.md` (add MCP client config snippet)
- Create: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: `server._prepare_note`, `_resolve_placement`, `_write_section`.
- Produces: an end-to-end test simulating the agent flow; documented MCP registration.

- [ ] **Step 1: Write the failing test**

`tests/test_end_to_end.py`:
```python
import fitz
from scribe_tex import server
from scribe_tex.placement import existing_dates


def test_full_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBE_TEX_NOTES_ROOT", str(tmp_path))
    # 1. prepare a (blank) note PDF
    pdf = tmp_path / "linalg.pdf"
    d = fitz.open(); d.new_page(); d.save(str(pdf)); d.close()
    prep = server._prepare_note("file", str(pdf))
    assert prep["page_images"]

    # 2. agent "transcribes" + infers -> resolve
    res = server._resolve_placement("MATH 257 Linear Algebra", "Oct 3 2025")
    assert res["course_status"] == "new"
    assert res["date_iso"] == "2025-10-03"

    # 3. write after user confirms
    w = server._write_section(res["course"], res["date_iso"],
                              r"\subsection{Vector spaces} A field...")
    assert w["written"] is True

    # 4. a second, earlier date lands before the first
    server._write_section("MATH 257 Linear Algebra", "2025-09-28", "intro")
    main_tex = (tmp_path / "MATH-257-Linear-Algebra" / "main.tex").read_text()
    assert existing_dates(main_tex) == ["2025-09-28", "2025-10-03"]
```

- [ ] **Step 2: Run test to verify it fails, then confirm whole suite**

Run: `python -m pytest tests/test_end_to_end.py -v`
Expected: PASS immediately (it exercises already-built code) — if it fails, fix the offending module, not the test.
Then run the full suite: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 3: Add MCP config docs to README**

Append to `README.md`:
```markdown
## Register with an MCP client

Add to your MCP client config (e.g. Claude Code `.mcp.json`):

```json
{
  "mcpServers": {
    "scribe-tex": {
      "command": "scribe-tex"
    }
  }
}
```

Or run directly: `python -m scribe_tex.server`.

## Workflow

1. Drop a handwritten note export path into chat: *"process ~/Downloads/linalg-oct3.pdf"*.
2. The agent calls `prepare_note`, reads the page images, transcribes to LaTeX,
   and infers the course + date.
3. The agent calls `resolve_placement` and shows you the detected course, date,
   target file, and whether that date already exists — you confirm.
4. The agent calls `write_section`; the note is filed into the course's
   `main.tex` as a dated section, in date order.
```

- [ ] **Step 4: Run full suite once more**

Run: `python -m pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_end_to_end.py README.md
git commit -m "test: end-to-end flow; docs: MCP registration"
```

---

## Self-Review

**Spec coverage:**
- NoteSource seam (FileSource + OneNote stub) → Task 9. ✓
- Agent-delegated transcription (brief, no LLM in server) → Task 10; server has no network/LLM. ✓
- prepare_note / resolve_placement / write_section → Tasks 12 (+ inputs from 3–11). ✓
- Infer-then-confirm → resolve returns `match_confidence`/`course_status`; confirm happens in-agent; write is a separate call. ✓
- One repo per course, auto-scaffold → Task 7 + `_write_section`. ✓
- Single main.tex, section per date, ISO label, ENTRIES markers → Tasks 6/7/8. ✓
- Date-order insertion → Task 6 `plan_insertion`, tested in 6/8/13. ✓
- Duplicate warn/replace/append (default warn) → Task 8. ✓
- Write-only (no compile) → `compiled: False`; no TeX calls anywhere. ✓
- Notes root env + default → Task 2, surfaced in prepare_note. ✓
- Preamble adaptation (drop subfiles, template footer/number, keep macros) → Task 3. ✓
- Repo local git only, README docs, no Pages → README in Tasks 1/13; no Pages tasks. ✓

**Placeholder scan:** No TBD/TODO; every code step has real code. ✓

**Type consistency:** `plan_insertion` keys (`duplicate`/`after_date`/`insert_index`) used consistently in Tasks 6/8/12. `match_course` returns `(name|None, confidence)` used in 5/12. `fetch_pages(ref)->list[Path]` consistent across 9/12. `course_slug` used in 5/7/12. `display_date`/`parse_date` consistent across 4/8/12. ✓

One intentional cross-task note: Task 12's `_resolve_placement` sets `match_confidence` for a *new* course to `high` when the date parses (a new course is still a confident placement target once named + dated); the `test_resolve_bad_date` case forces `low` via an unparseable date. This is consistent with the spec's "low confidence or new → agent asks," since the agent still confirms new-course folder names in chat regardless of confidence.
