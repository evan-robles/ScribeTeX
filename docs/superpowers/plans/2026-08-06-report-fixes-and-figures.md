# ScribeTeX Field-Report Fixes + Figures Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the real issues from the field report (self-locating scripts, doubled command paths, error strings, date-only duplicate collisions) and add a figures capability (pgfplots + a `save_figure` crop tool + a TikZ-first brief).

**Architecture:** ScribeTeX is a FastMCP stdio server (`src/scribetex/`) plus four self-contained skills (`skills/*/scripts/run.py`) and plugin manifests. Transcription placement is pure-string logic in `placement.py`/`writer.py`; sources render pages in `sources/`; the server exposes MCP tools. Fixes touch these modules plus the brief and preamble; the figures feature adds one MCP tool backed by Pillow.

**Tech Stack:** Python 3, FastMCP, PyMuPDF (`fitz`), Pillow, python-dateutil, pytest.

## Global Constraints

- Work in the worktree `~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures` on branch `fix-report-and-figures`. Run pytest with `PYTHONPATH=src` from the worktree root (repo config sets `pythonpath=["src"]`, so `pytest` alone also works from the root).
- Duplicate-detection label format is `\label{note:<date>:<section-slug>:<subsection-slug>}`. Slugs are lowercase, non-alphanumerics→hyphens, collapsed, stripped. Existing date-only labels (`\label{note:2026-08-06}`) must still be *found* by the widened regex and must NOT false-collide with composite keys.
- `save_figure` bbox is `[x0, y0, x1, y1]` as fractions in `[0,1]` of page width/height, origin top-left. Validate `0 <= x0 < x1 <= 1` and `0 <= y0 < y1 <= 1`.
- Figure priority the brief enforces: **TikZ/pgfplots/tabular → embed crop via `save_figure` → prose.**
- Only `Evan S. Robles` and `University of Chicago` are hardcoded identity; course name/number stay flexible (unchanged from current code).
- Version is bumped to `0.2.0` in all three manifests in the final task, not piecemeal.
- Every `run.py` must import `scribetex` with `PYTHONPATH` unset (self-locating).
- Do not reimplement: `classify.course_slug`, `config.notes_root`, `scaffold.scaffold_course` (already creates `ExtFiles/`), the existing `placement`/`writer` structure.

---

### Task 1: Better error strings in FileSource (§3.1)

**Files:**
- Modify: `src/scribetex/sources/file_source.py`
- Test: `tests/test_file_source_errors.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces: `FileSource.fetch_pages(ref)` raising named errors: empty ref → `ValueError` message starting `"no note path provided:"`; missing file → `FileNotFoundError` message starting `"file not found:"`; bad ext → `ValueError` message starting `"unsupported extension"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_file_source_errors.py
import pytest
from scribetex.sources.file_source import FileSource


def test_empty_ref_names_the_field():
    with pytest.raises(ValueError, match=r"no note path provided: pass ref="):
        FileSource().fetch_pages("")


def test_blank_ref_names_the_field():
    with pytest.raises(ValueError, match=r"no note path provided"):
        FileSource().fetch_pages("   ")


def test_missing_file_message(tmp_path):
    missing = tmp_path / "nope.pdf"
    with pytest.raises(FileNotFoundError, match=r"file not found:.*nope\.pdf"):
        FileSource().fetch_pages(str(missing))


def test_unsupported_extension_lists_supported(tmp_path):
    f = tmp_path / "note.foo"
    f.write_text("x")
    with pytest.raises(ValueError, match=r"unsupported extension '\.foo'; supported: pdf, png, jpg, jpeg, heic"):
        FileSource().fetch_pages(str(f))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && PYTHONPATH=src python -m pytest tests/test_file_source_errors.py -v`
Expected: FAIL (current code raises `ValueError(f"unsupported note file type: {ext}")` and a bare `FileNotFoundError(path)`, and does not special-case empty ref).

- [ ] **Step 3: Write minimal implementation**

Edit `fetch_pages` in `src/scribetex/sources/file_source.py` so the top of the method reads:

```python
    def fetch_pages(self, ref: str) -> list[Path]:
        if not (ref or "").strip():
            raise ValueError("no note path provided: pass ref=<path to PDF/image>")
        path = Path(ref).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"file not found: {path}")
        ext = path.suffix.lower()
        if ext in _IMAGE_EXTS:
            return [path]
        if ext != ".pdf":
            raise ValueError(
                f"unsupported extension '{ext}'; supported: pdf, png, jpg, jpeg, heic"
            )
        import fitz  # PyMuPDF
        ...  # rest unchanged
```

(Leave the PDF-render body below unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && PYTHONPATH=src python -m pytest tests/test_file_source_errors.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/test_file_source_errors.py src/scribetex/sources/file_source.py
git commit -m "fix: name the field and fix in FileSource error messages (report 3.1)"
```

---

### Task 2: Self-locating run.py in all four skills (§1.2) + fix SKILL.md command paths (§1.3)

**Files:**
- Modify: `skills/process-note/scripts/run.py`, `skills/new-course/scripts/run.py`, `skills/list-courses/scripts/run.py`, `skills/compile-course/scripts/run.py`
- Modify: `skills/process-note/SKILL.md`, `skills/new-course/SKILL.md`, `skills/list-courses/SKILL.md`, `skills/compile-course/SKILL.md`
- Test: `tests/test_run_self_locating.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: each `run.py` importable via subprocess with `PYTHONPATH` cleared from the environment.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_self_locating.py
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = ["process-note", "new-course", "list-courses", "compile-course"]


def _run_help(skill: str):
    script = REPO / "skills" / skill / "scripts" / "run.py"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True, text=True, env=env, cwd=str(Path.home()),
    )


def test_every_run_imports_without_pythonpath():
    for skill in SKILLS:
        r = _run_help(skill)
        # --help exits 0 after argparse prints usage; a broken import exits 1
        # with ModuleNotFoundError on stderr.
        assert "ModuleNotFoundError" not in r.stderr, f"{skill}: {r.stderr}"
        assert r.returncode == 0, f"{skill} rc={r.returncode}: {r.stderr}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_run_self_locating.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scribetex'` for each skill (PYTHONPATH is stripped).

- [ ] **Step 3: Write minimal implementation**

In EACH of the four `scripts/run.py`, insert this block immediately after the existing `import` lines and BEFORE the first `from scribetex import ...`:

```python
import pathlib
_SRC = pathlib.Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
```

Requirements per file:
- Ensure `import sys` and `import pathlib` are present (add if missing; `process-note/run.py` already imports `sys`).
- The block must appear before any `from scribetex ...` import. If a file does `from scribetex import ...` at module top, move that import below the block.

Also update each `SKILL.md`: every command that reads `python skills/<name>/scripts/run.py ...` becomes `python scripts/run.py ...` (relative to the skill's own base dir). Update both the Instructions code block and the Examples block. Update the docstring line in each `run.py` that says "the plugin sets PYTHONPATH" to: `"Self-locating: prepends ../../../src to sys.path, so no external PYTHONPATH is required."`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_run_self_locating.py -v`
Expected: PASS.

Also grep to confirm no doubled paths remain:
Run: `grep -rn "python skills/" skills/*/SKILL.md`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add skills/*/scripts/run.py skills/*/SKILL.md tests/test_run_self_locating.py
git commit -m "fix: self-locating run.py + relative SKILL.md commands (report 1.2, 1.3)"
```

---

### Task 3: Composite note-key helpers in placement.py (§2.2)

**Files:**
- Modify: `src/scribetex/placement.py`
- Test: `tests/test_placement_keys.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `note_slug(text: str) -> str` — lowercase, non-`[a-z0-9]`→`-`, collapse repeats, strip leading/trailing `-`. Empty input → `""`.
  - `note_key(date_iso: str, section_title: str, subsection_title: str) -> str` — returns `f"{date_iso}:{note_slug(section_title)}:{note_slug(subsection_title)}"`.
  - `subsection_block(title, body, date_iso, section_title)` — signature GAINS `section_title`; emits `\label{note:<note_key>}`.
  - `existing_note_labels(main_tex) -> list[str]` — returns the full key strings after `note:` (composite OR legacy date-only), in document order.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_placement_keys.py
from scribetex import placement as P


def test_note_slug_basic():
    assert P.note_slug("Muscles and Movement") == "muscles-and-movement"
    assert P.note_slug("  Réceptors!!  ") == "r-ceptors"
    assert P.note_slug("") == ""
    assert P.note_slug("---A---B---") == "a-b"


def test_note_key_composite():
    assert P.note_key("2026-08-06", "Muscles and Movement", "Muscles") == \
        "2026-08-06:muscles-and-movement:muscles"


def test_subsection_block_uses_composite_label():
    block = P.subsection_block("Muscles", "body text", "2026-08-06", "Muscles and Movement")
    assert r"\label{note:2026-08-06:muscles-and-movement:muscles}" in block
    assert "body text" in block
    assert r"\subsection{Muscles}" in block


def test_existing_note_labels_reads_composite_and_legacy():
    tex = (
        r"\label{note:2026-08-06:muscles-and-movement:muscles}" "\n"
        r"\label{note:2025-01-02}" "\n"
    )
    assert P.existing_note_labels(tex) == [
        "2026-08-06:muscles-and-movement:muscles",
        "2025-01-02",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_placement_keys.py -v`
Expected: FAIL (`note_slug`/`note_key` do not exist; `subsection_block` has the old 3-arg signature; `existing_note_labels` regex only matches date-only).

- [ ] **Step 3: Write minimal implementation**

In `src/scribetex/placement.py`:

Replace the label regex and add helpers:

```python
_SECTION_RE = re.compile(r"\\section\{(.*?)\}")
# Composite key: date, then optional :section-slug:subsection-slug. Legacy
# date-only labels (no colons after the date) are matched too.
_NOTE_LABEL_RE = re.compile(r"\\label\{note:(\d{4}-\d{2}-\d{2}(?::[a-z0-9-]*){0,2})\}")


def note_slug(text: str) -> str:
    """Lowercase, hyphenated, ASCII-safe reduction of a title for a note key."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower())
    return s.strip("-")


def note_key(date_iso: str, section_title: str, subsection_title: str) -> str:
    """Composite duplicate-detection key: date + section slug + subsection slug."""
    return f"{date_iso}:{note_slug(section_title)}:{note_slug(subsection_title)}"
```

Update `existing_note_labels` docstring to "keys" and keep it returning `_NOTE_LABEL_RE.findall(...)` (regex now captures the composite group).

Change `subsection_block`:

```python
def subsection_block(title: str, body: str, date_iso: str, section_title: str) -> str:
    """A single ``\\subsection`` with a hidden composite note-label + body markers."""
    key = note_key(date_iso, section_title, title)
    return (
        f"\\subsection{{{title}}}\n"
        f"\\label{{note:{key}}}\n"
        f"{BODY_BEGIN}\n"
        f"{body}\n"
        f"{BODY_END}\n"
    )
```

Note: `subsection_block`'s subsection title IS the subsection used in the key (its first arg `title`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_placement_keys.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scribetex/placement.py tests/test_placement_keys.py
git commit -m "feat: composite note-key helpers (date+section+subsection) in placement (report 2.2)"
```

---

### Task 4: Re-key writer.py duplicate detection on the composite key (§2.2)

**Files:**
- Modify: `src/scribetex/writer.py`
- Test: `tests/test_writer_composite_dupes.py` (create)

**Interfaces:**
- Consumes: `placement.note_key`, `placement.existing_note_labels`, `placement.subsection_block` (4-arg).
- Produces:
  - `insert_note(main_tex, section_title, subsection_title, body, date_iso, on_duplicate="warn")` — unchanged signature; now keys duplicate check on `note_key(date_iso, section_title, subsection_title)`.
  - `DuplicateNoteError(date_iso, section_title, subsection_title)` — message: `"a note for section '<section>' / subsection '<subsection>' on <date> already exists"`; keeps `.date_iso`, adds `.section_title`, `.subsection_title`.
  - `_replace_note(main_tex, subsection_title, body, date_iso, section_title)` — matches the composite label.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_writer_composite_dupes.py
import pytest
from scribetex import writer
from scribetex.placement import ENTRIES_START, ENTRIES_END

EMPTY = f"HEAD\n{ENTRIES_START}\n{ENTRIES_END}\nTAIL\n"


def _insert(tex, section, sub, body, date, dup="warn"):
    return writer.insert_note(tex, section, sub, body, date, dup)


def test_same_day_different_topic_not_duplicate():
    tex, _ = _insert(EMPTY, "Receptors", "Receptors", "b1", "2026-08-06")
    # Same date, DIFFERENT section + subsection -> must NOT be a duplicate.
    tex2, summary = _insert(tex, "Muscles and Movement", "Muscles", "b2", "2026-08-06")
    assert r"\subsection{Receptors}" in tex2
    assert r"\subsection{Muscles}" in tex2
    assert "b1" in tex2 and "b2" in tex2


def test_exact_same_key_is_duplicate():
    tex, _ = _insert(EMPTY, "Receptors", "Receptors", "b1", "2026-08-06")
    with pytest.raises(writer.DuplicateNoteError) as ei:
        _insert(tex, "Receptors", "Receptors", "b2", "2026-08-06")
    msg = str(ei.value)
    assert "Receptors" in msg and "2026-08-06" in msg


def test_replace_collapses_only_matching_key():
    tex, _ = _insert(EMPTY, "Receptors", "Receptors", "b1", "2026-08-06")
    tex, _ = _insert(tex, "Muscles", "Muscles", "keep-me", "2026-08-06")
    tex2, summary = _insert(tex, "Receptors", "Receptors", "b1-v2", "2026-08-06", dup="replace")
    assert "b1-v2" in tex2
    assert "b1" not in tex2.replace("b1-v2", "")  # old Receptors body gone
    assert "keep-me" in tex2                        # Muscles untouched
    assert "replaced" in summary


def test_append_adds_second_subsection_same_key():
    tex, _ = _insert(EMPTY, "Receptors", "Receptors", "b1", "2026-08-06")
    tex2, _ = _insert(tex, "Receptors", "Receptors", "b2", "2026-08-06", dup="append")
    assert tex2.count(r"\label{note:2026-08-06:receptors:receptors}") == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_writer_composite_dupes.py -v`
Expected: FAIL — current `insert_note` keys on `date_iso in existing_note_labels(...)` (date-only) so `test_same_day_different_topic_not_duplicate` raises `DuplicateNoteError`; and `subsection_block`/`_replace_note` calls use the old signatures.

- [ ] **Step 3: Write minimal implementation**

In `src/scribetex/writer.py`:

Update imports to include `note_key`:

```python
from .placement import (
    ENTRIES_START, ENTRIES_END, BODY_END,
    plan_topic_insertion, subsection_block, section_block, existing_note_labels,
    note_key,
)
```

Rework `DuplicateNoteError`:

```python
class DuplicateNoteError(Exception):
    def __init__(self, date_iso: str, section_title: str, subsection_title: str):
        super().__init__(
            f"a note for section '{section_title}' / subsection "
            f"'{subsection_title}' on {date_iso} already exists"
        )
        self.date_iso = date_iso
        self.section_title = section_title
        self.subsection_title = subsection_title
```

Rework `_replace_note` to take and match the composite label:

```python
def _replace_note(main_tex: str, subsection_title: str, body: str,
                  date_iso: str, section_title: str) -> str:
    key = note_key(date_iso, section_title, subsection_title)
    label = f"\\label{{note:{key}}}"
    spans = []
    search_from = 0
    while True:
        label_pos = main_tex.find(label, search_from)
        if label_pos == -1:
            break
        sub_pos = main_tex.rindex("\\subsection{", 0, label_pos)
        end_pos = main_tex.index(BODY_END, label_pos)
        block_end = main_tex.index("\n", end_pos) + 1
        spans.append((sub_pos, block_end))
        search_from = block_end

    result = main_tex
    for sub_pos, block_end in reversed(spans):
        result = result[:sub_pos] + result[block_end:]

    insert_at = spans[0][0]
    block = subsection_block(subsection_title, body, date_iso, section_title)
    return result[:insert_at] + block + result[insert_at:]
```

Rework `insert_note` duplicate check and all `subsection_block` calls:

```python
def insert_note(main_tex: str, section_title: str, subsection_title: str,
                body: str, date_iso: str,
                on_duplicate: str = "warn") -> tuple[str, str]:
    _require_markers(main_tex)

    key = note_key(date_iso, section_title, subsection_title)
    if key in existing_note_labels(main_tex):
        if on_duplicate == "warn":
            raise DuplicateNoteError(date_iso, section_title, subsection_title)
        if on_duplicate == "replace":
            new = _replace_note(main_tex, subsection_title, body, date_iso, section_title)
            return new, f"replaced note '{subsection_title}' under '{section_title}' ({date_iso})"
        if on_duplicate == "append":
            pass
        else:
            raise ValueError(f"unknown on_duplicate: {on_duplicate}")

    plan = plan_topic_insertion(main_tex, section_title)
    sub = subsection_block(subsection_title, body, date_iso, section_title)
    # ... rest unchanged (section_exists branch etc.)
```

Ensure BOTH `subsection_block(...)` calls in `insert_note` pass `section_title`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_writer_composite_dupes.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/scribetex/writer.py tests/test_writer_composite_dupes.py
git commit -m "feat: writer keys duplicates on composite key; error names the collision (report 2.2)"
```

---

### Task 5: Align resolve_placement with the composite key + add subsection_hint (§2.3)

**Files:**
- Modify: `src/scribetex/server.py` (`_resolve_placement`, `resolve_placement` tool, and SERVER_INSTRUCTIONS step 3)
- Test: `tests/test_resolve_predicts_write.py` (create)

**Interfaces:**
- Consumes: `placement.note_key`, `placement.existing_note_labels`.
- Produces: `_resolve_placement(course_hint, section_hint, subsection_hint, date) -> dict` — GAINS `subsection_hint`; the returned `duplicate` bool is computed as `note_key(date_iso, section_hint, subsection_hint) in existing_note_labels(text)`. The `resolve_placement` MCP tool gains the matching `subsection_hint` parameter (positioned after `section_hint`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_resolve_predicts_write.py
import pytest
from scribetex import server
from scribetex.writer import insert_note, DuplicateNoteError


def _course(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))


def test_resolve_duplicate_matches_write_outcome(tmp_path, monkeypatch):
    _course(tmp_path, monkeypatch)
    # First write scaffolds + inserts.
    r1 = server._write_section("Bio", "Receptors", "Receptors", "b1", "2026-08-06", "BIOS 20200")
    assert r1["written"] is True

    # Same date, DIFFERENT subsection: resolve says not-duplicate AND write succeeds.
    res = server._resolve_placement("Bio", "Muscles and Movement", "Muscles", "2026-08-06")
    assert res["duplicate"] is False
    r2 = server._write_section("Bio", "Muscles and Movement", "Muscles", "b2", "2026-08-06", "BIOS 20200")
    assert r2["written"] is True

    # Same date + section + subsection: resolve says duplicate AND write refuses.
    res2 = server._resolve_placement("Bio", "Receptors", "Receptors", "2026-08-06")
    assert res2["duplicate"] is True
    r3 = server._write_section("Bio", "Receptors", "Receptors", "b1-again", "2026-08-06", "BIOS 20200")
    assert r3["written"] is False


def test_resolve_reports_subsection_in_payload(tmp_path, monkeypatch):
    _course(tmp_path, monkeypatch)
    res = server._resolve_placement("Bio", "Receptors", "Receptors", "2026-08-06")
    assert res["subsection_title"] == "Receptors"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_resolve_predicts_write.py -v`
Expected: FAIL — `_resolve_placement` currently takes 3 args (no `subsection_hint`) and keys `duplicate` on date-only, so the signature call raises `TypeError` and/or the duplicate prediction disagrees with write.

- [ ] **Step 3: Write minimal implementation**

In `src/scribetex/server.py`:

Add `note_key` to the placement import:

```python
from .placement import existing_sections, existing_note_labels, note_key
```

Change `_resolve_placement` signature and duplicate logic:

```python
def _resolve_placement(course_hint: str, section_hint: str,
                       subsection_hint: str, date: str) -> dict:
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
        confidence = "high" if date_iso else "low"

    slug = course_slug(course)
    target = root / slug / "main.tex"

    duplicate = False
    section_status = "new"
    sections: list[str] = []
    if status == "existing" and target.exists():
        text = target.read_text(encoding="utf-8")
        sections = existing_sections(text)
        section_status = "existing" if section_hint in sections else "new"
        if date_iso:
            key = note_key(date_iso, section_hint, subsection_hint)
            duplicate = key in existing_note_labels(text)

    if not date_iso:
        confidence = "low"

    return {
        "course": course,
        "course_status": status,
        "section_title": section_hint,
        "subsection_title": subsection_hint,
        "section_status": section_status,
        "existing_sections": sections,
        "target_path": str(target),
        "date_iso": date_iso,
        "date_display": display_date(date_iso) if date_iso else None,
        "duplicate": duplicate,
        "match_confidence": confidence,
    }
```

Update the `resolve_placement` MCP tool signature and docstring to add `subsection_hint` (after `section_hint`), and pass it through:

```python
@mcp.tool
def resolve_placement(course_hint: str, section_hint: str,
                      subsection_hint: str, date: str) -> dict:
    """... (update Args to document subsection_hint: the concise SUBSECTION
    title for THIS note; used with section + date to predict duplicates
    exactly as write_section will). ..."""
    return _resolve_placement(course_hint, section_hint, subsection_hint, date)
```

Update SERVER_INSTRUCTIONS STEP 3 line to include `subsection_hint=...` in the documented call and note that `duplicate` now keys on date+section+subsection (so it predicts `write_section` exactly).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_resolve_predicts_write.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scribetex/server.py tests/test_resolve_predicts_write.py
git commit -m "fix: resolve_placement takes subsection_hint and predicts write duplicates exactly (report 2.3)"
```

---

### Task 6: Add pgfplots to the preamble + allowed list (figures)

**Files:**
- Modify: `src/scribetex/preamble.py`
- Test: `tests/test_preamble_pgfplots.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `render_preamble(...)` output contains `\usepackage{pgfplots}` and `\pgfplotsset{compat=1.18}`; `ALLOWED_PACKAGES` contains `"pgfplots"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preamble_pgfplots.py
from scribetex.preamble import render_preamble, ALLOWED_PACKAGES


def test_pgfplots_loaded_and_configured():
    tex = render_preamble(footer_name="Robles", course_number="BIOS 20200")
    assert r"\usepackage{pgfplots}" in tex
    assert r"\pgfplotsset{compat=1.18}" in tex


def test_pgfplots_in_allowed_list():
    assert "pgfplots" in ALLOWED_PACKAGES


def test_preamble_still_renders_fields():
    tex = render_preamble(footer_name="Robles", course_number="BIOS 20200")
    assert "BIOS 20200" in tex
    assert "Robles" in tex
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_preamble_pgfplots.py -v`
Expected: FAIL (pgfplots not present).

- [ ] **Step 3: Write minimal implementation**

In `src/scribetex/preamble.py`, inside `PREAMBLE_BODY`, immediately AFTER the `\usetikzlibrary{{...}}` block (the block ending `}}` before `\usepackage{{float}}`), insert two lines (braces DOUBLED for `str.format`):

```
\usepackage{{pgfplots}}
\pgfplotsset{{compat=1.18}}
```

Add `"pgfplots"` to `ALLOWED_PACKAGES` (e.g. right after `"tikz"`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_preamble_pgfplots.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scribetex/preamble.py tests/test_preamble_pgfplots.py
git commit -m "feat: add pgfplots to preamble and allowed packages (figures)"
```

---

### Task 7: `figures.py` — crop a page region to ExtFiles/ (figures)

**Files:**
- Create: `src/scribetex/figures.py`
- Test: `tests/test_figures.py` (create)

**Interfaces:**
- Consumes: `classify.course_slug`, `config.notes_root`.
- Produces:
  - `sanitize_name(name: str) -> str` — keep `[A-Za-z0-9_-]`, others→`-`, strip, collapse; empty → `"figure"`.
  - `validate_bbox(bbox) -> tuple[float,float,float,float]` — accepts a 4-sequence; raises `ValueError` (message starting `"invalid bbox"`) unless `0 <= x0 < x1 <= 1` and `0 <= y0 < y1 <= 1`.
  - `crop_to_extfiles(page_image, bbox, course, name, root=None) -> dict` — opens the PNG with Pillow, converts fractional bbox → pixel box via the image's own size, crops, ensures `<root>/<course-slug>/ExtFiles/` exists, writes `<name>.png` there, returns `{"saved": True, "filename": "<name>.png", "path": "<abs>"}`. Missing page image → `FileNotFoundError(f"page image not found: {path}")`. `root` defaults to `config.notes_root()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_figures.py
import pytest
from PIL import Image
from scribetex import figures


def _make_png(tmp_path, w=200, h=100):
    p = tmp_path / "page.png"
    Image.new("RGB", (w, h), "white").save(p)
    return p


def test_sanitize_name():
    assert figures.sanitize_name("Fig 1: Curve!") == "Fig-1-Curve"
    assert figures.sanitize_name("") == "figure"
    assert figures.sanitize_name("a/b\\c") == "a-b-c"


def test_validate_bbox_ok():
    assert figures.validate_bbox([0.1, 0.2, 0.9, 0.8]) == (0.1, 0.2, 0.9, 0.8)


@pytest.mark.parametrize("bad", [
    [0.5, 0, 0.5, 1],     # x0 == x1
    [0, 0, 1, 0],         # y0 == y1
    [-0.1, 0, 1, 1],      # x0 < 0
    [0, 0, 1.1, 1],       # x1 > 1
    [0.9, 0, 0.1, 1],     # x0 > x1
])
def test_validate_bbox_rejects(bad):
    with pytest.raises(ValueError, match="invalid bbox"):
        figures.validate_bbox(bad)


def test_crop_writes_to_extfiles(tmp_path):
    page = _make_png(tmp_path, w=200, h=100)
    root = tmp_path / "notes"
    res = figures.crop_to_extfiles(
        str(page), [0.0, 0.0, 0.5, 1.0], "Bio 101", "diagram", root=root,
    )
    assert res["saved"] is True
    assert res["filename"] == "diagram.png"
    out = root / "Bio-101" / "ExtFiles" / "diagram.png"
    assert out.exists()
    # Half width, full height -> 100 x 100.
    assert Image.open(out).size == (100, 100)


def test_crop_missing_page(tmp_path):
    with pytest.raises(FileNotFoundError, match="page image not found"):
        figures.crop_to_extfiles(str(tmp_path / "nope.png"), [0, 0, 1, 1], "Bio", "d", root=tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_figures.py -v`
Expected: FAIL (`scribetex.figures` does not exist).

- [ ] **Step 3: Write minimal implementation**

Create `src/scribetex/figures.py`:

```python
"""Crop a rendered page region into a course's ExtFiles/ for \\includegraphics."""
from __future__ import annotations
import re
from pathlib import Path

from .classify import course_slug
from .config import notes_root


def sanitize_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", (name or "")).strip("-")
    return s or "figure"


def validate_bbox(bbox) -> tuple[float, float, float, float]:
    try:
        x0, y0, x1, y1 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        raise ValueError("invalid bbox: expected [x0, y0, x1, y1] fractions in [0,1]")
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        raise ValueError(
            "invalid bbox: need 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1; "
            f"got {bbox}"
        )
    return x0, y0, x1, y1


def crop_to_extfiles(page_image: str, bbox, course: str, name: str,
                     root: Path | None = None) -> dict:
    from PIL import Image
    page = Path(page_image).expanduser()
    if not page.exists():
        raise FileNotFoundError(f"page image not found: {page}")
    x0, y0, x1, y1 = validate_bbox(bbox)
    base = (root if root is not None else notes_root())
    ext_dir = Path(base) / course_slug(course) / "ExtFiles"
    ext_dir.mkdir(parents=True, exist_ok=True)

    img = Image.open(page)
    w, h = img.size
    box = (round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h))
    crop = img.crop(box)
    fname = f"{sanitize_name(name)}.png"
    out = ext_dir / fname
    crop.save(out)
    return {"saved": True, "filename": fname, "path": str(out)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_figures.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scribetex/figures.py tests/test_figures.py
git commit -m "feat: figures.crop_to_extfiles crops a page region into ExtFiles/ (figures)"
```

---

### Task 8: `save_figure` MCP tool + Pillow dependency (figures)

**Files:**
- Modify: `src/scribetex/server.py` (add `_save_figure` helper + `save_figure` tool + SERVER_INSTRUCTIONS mention)
- Modify: `pyproject.toml` (add `pillow>=10`)
- Modify: `scripts/bootstrap_deps.py` (add PIL import check)
- Test: `tests/test_save_figure_tool.py` (create)

**Interfaces:**
- Consumes: `figures.crop_to_extfiles`.
- Produces: `_save_figure(course, page_image, bbox, name) -> dict` returning `figures.crop_to_extfiles(...)` plus `"include"` (a ready `\includegraphics[width=0.8\linewidth]{<name>}` snippet), or `{"saved": False, "error": ...}` on `FileNotFoundError`/`ValueError`. The `save_figure` MCP tool wraps it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_save_figure_tool.py
from PIL import Image
from scribetex import server


def _png(tmp_path):
    p = tmp_path / "p1.png"
    Image.new("RGB", (300, 200), "white").save(p)
    return p


def test_save_figure_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))
    page = _png(tmp_path)
    res = server._save_figure("Bio 101", str(page), [0.0, 0.0, 1.0, 0.5], "curve")
    assert res["saved"] is True
    assert res["filename"] == "curve.png"
    assert "includegraphics" in res["include"]
    assert "curve" in res["include"]
    assert (tmp_path / "Bio-101" / "ExtFiles" / "curve.png").exists()


def test_save_figure_bad_bbox_returns_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))
    page = _png(tmp_path)
    res = server._save_figure("Bio 101", str(page), [0, 0, 0, 1], "curve")
    assert res["saved"] is False
    assert "invalid bbox" in res["error"]


def test_save_figure_missing_page_returns_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))
    res = server._save_figure("Bio 101", str(tmp_path / "nope.png"), [0, 0, 1, 1], "c")
    assert res["saved"] is False
    assert "page image not found" in res["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_save_figure_tool.py -v`
Expected: FAIL (`_save_figure` does not exist).

- [ ] **Step 3: Write minimal implementation**

In `src/scribetex/server.py`, add the import and helper:

```python
from . import figures
```

```python
def _save_figure(course: str, page_image: str, bbox, name: str) -> dict:
    try:
        res = figures.crop_to_extfiles(page_image, bbox, course, name)
    except (FileNotFoundError, ValueError) as e:
        return {"saved": False, "error": str(e)}
    res["include"] = f"\\includegraphics[width=0.8\\linewidth]{{{res['filename'][:-4]}}}"
    return res
```

Add the tool:

```python
@mcp.tool
def save_figure(course: str, page_image: str, bbox: list[float], name: str) -> dict:
    """Crop a region of a rendered note page into the course's ExtFiles/ so a
    freehand drawing can be embedded with \\includegraphics. Use this only when a
    figure cannot be faithfully reproduced as TikZ/pgfplots/tabular.

    Args:
        course: the course NAME (same value you pass to write_section); the crop
            is written under that course's ExtFiles/.
        page_image: absolute path to a page PNG returned by prepare_note.
        bbox: [x0, y0, x1, y1] as fractions in [0,1] of the page width/height,
            origin top-left (e.g. [0.1, 0.4, 0.9, 0.7] = a middle horizontal band).
        name: base filename (no extension); sanitized to [A-Za-z0-9_-].
    Returns {"saved": true, filename, path, include (a ready \\includegraphics
    snippet)} or {"saved": false, "error": ...}. \\graphicspath already points at
    ExtFiles/, so \\includegraphics{<name>} resolves without a path prefix."""
    return _save_figure(course, page_image, bbox, name)
```

Add a short line to SERVER_INSTRUCTIONS (in STEP 2, transcription) noting the TikZ → save_figure → prose priority and that `save_figure` embeds a cropped drawing.

In `pyproject.toml`, add `"pillow>=10"` to `dependencies`.

In `scripts/bootstrap_deps.py`, add PIL to the checked imports (import name `PIL`, pip name `pillow`). Follow the file's existing pattern for the (import-name, pip-name) pairs.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_save_figure_tool.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scribetex/server.py pyproject.toml scripts/bootstrap_deps.py tests/test_save_figure_tool.py
git commit -m "feat: save_figure MCP tool crops drawings into ExtFiles/; add pillow dep (figures)"
```

---

### Task 9: Rewrite the transcription brief for the figure priority (figures)

**Files:**
- Modify: `src/scribetex/transcription_brief.py`
- Test: `tests/test_brief_figures.py` (create)

**Interfaces:**
- Consumes: `ALLOWED_PACKAGES`, `ALLOWED_MACROS`.
- Produces: `build_brief()` output that (a) lists the TikZ → save_figure → prose priority, (b) names `pgfplots`, `tabular`/`booktabs`, and `save_figure`, (c) documents the fractional bbox convention, (d) still instructs body-only output and separate extraction of course/section/subsection/date.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_brief_figures.py
from scribetex.transcription_brief import build_brief


def test_brief_states_figure_priority():
    b = build_brief().lower()
    assert "tikz" in b and "pgfplots" in b
    assert "save_figure" in b
    assert "prose" in b
    # priority ordering mentioned
    assert b.index("tikz") < b.index("save_figure") < b.index("prose")


def test_brief_documents_bbox_fractions():
    b = build_brief()
    assert "x0" in b and "x1" in b
    assert "0" in b and "1" in b  # fractions in [0,1]


def test_brief_still_body_only_and_extracts():
    b = build_brief()
    assert "BODY ONLY" in b
    assert "subsection" in b and "section" in b and "date" in b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_brief_figures.py -v`
Expected: FAIL (current brief has no `save_figure`/`pgfplots`/bbox text).

- [ ] **Step 3: Write minimal implementation**

In `src/scribetex/transcription_brief.py`, replace the single hand-drawn-diagram line with a FIGURES block, and keep everything else. The returned string must include (verbatim substrings the test checks): `BODY ONLY`, `TikZ`, `pgfplots`, `save_figure`, `prose`, `x0`, `x1`, and continue to mention `section`, `subsection`, `date`. Suggested replacement inserted where the old "Render hand-drawn diagrams..." line was:

```python
        "FIGURES (charts, tables, graphs, plots, drawings) — follow this order:\n"
        "  1. If it is data/structured (a chart, table, graph, plot, labelled "
        "diagram), reproduce it faithfully as TikZ / pgfplots / tabular "
        "(booktabs) — all loaded.\n"
        "  2. If it cannot be faithfully reproduced that way (freehand drawing), "
        "embed a cropped image: call the save_figure tool with the page image "
        "path and a bounding box [x0, y0, x1, y1] as fractions in [0,1] of the "
        "page (origin top-left), then \\includegraphics{<returned filename>}.\n"
        "  3. Only if neither is possible, describe it in prose.\n"
        "  Tell the user which figures were drawn as TikZ, embedded as images, "
        "or described in prose.\n"
```

Ensure `pgfplots` also appears via the packages list (it will once Task 6 adds it to `ALLOWED_PACKAGES`), but the explicit mention above guarantees the test passes regardless of ordering.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_brief_figures.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scribetex/transcription_brief.py tests/test_brief_figures.py
git commit -m "feat: brief enforces TikZ -> save_figure -> prose figure priority (figures)"
```

---

### Task 10: MCP schema-shape + import smoke tests (§5.1/§5.2)

**Files:**
- Create: `tests/test_tool_schemas.py`
- Create: `tests/test_import_smoke.py`

**Interfaces:**
- Consumes: `server.mcp` (FastMCP). Tool schema is read via `await server.mcp.get_tool(name)` then `.parameters["properties"]` (dict of param name → schema). This API was verified in this repo.
- Produces: tests only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tool_schemas.py
import asyncio
from scribetex import server

EXPECTED = {
    "prepare_note": {"source", "ref"},
    "resolve_placement": {"course_hint", "section_hint", "subsection_hint", "date"},
    "write_section": {"course", "section_title", "subsection_title",
                      "latex_body", "date", "course_number", "on_duplicate"},
    "save_figure": {"course", "page_image", "bbox", "name"},
}


def _props(name):
    async def go():
        tool = await server.mcp.get_tool(name)
        return set(tool.parameters["properties"].keys())
    return asyncio.run(go())


def test_every_tool_exposes_expected_params():
    for name, expected in EXPECTED.items():
        props = _props(name)
        missing = expected - props
        assert not missing, f"{name} missing params: {missing} (has {props})"
```

```python
# tests/test_import_smoke.py
def test_import_package_and_server():
    import scribetex  # noqa: F401
    from scribetex import server  # noqa: F401
    assert hasattr(server, "mcp")
    assert hasattr(server, "main")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_tool_schemas.py tests/test_import_smoke.py -v`
Expected: `test_import_smoke` PASSES already; `test_tool_schemas` PASSES only if Tasks 5 and 8 landed (subsection_hint + save_figure). If run in order after Task 8, both pass — but write the test now so it locks the contract. If a task is missing it FAILS naming the missing params.

Note: this task runs AFTER Tasks 5 and 8, so both should pass. If `test_tool_schemas` fails, the failure names exactly which tool/param regressed — fix the offending tool, do not weaken the test.

- [ ] **Step 3: Write minimal implementation**

No production code — these are guard tests. If `test_tool_schemas` fails, the earlier task's tool signature is wrong; fix it there.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_tool_schemas.py tests/test_import_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_tool_schemas.py tests/test_import_smoke.py
git commit -m "test: MCP tool schema-shape + import smoke guards (report 5.1, 5.2)"
```

---

### Task 11: Version bump to 0.2.0 + README (figures + install refresh)

**Files:**
- Modify: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: all three manifests report version `0.2.0`; README documents `save_figure` and the figure workflow.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_version_bump.py
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_all_manifests_are_0_2_0():
    pj = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    mp = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert pj["version"] == "0.2.0"
    assert mp["plugins"][0]["version"] == "0.2.0"
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert re.search(r'^version\s*=\s*"0\.2\.0"', pyproject, re.M)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_version_bump.py -v`
Expected: FAIL (still 0.1.0).

- [ ] **Step 3: Write minimal implementation**

- `.claude-plugin/plugin.json`: `"version": "0.1.0"` → `"0.2.0"`.
- `.claude-plugin/marketplace.json`: the plugin entry's `"version": "0.1.0"` → `"0.2.0"`.
- `pyproject.toml`: `version = "0.1.0"` → `"0.2.0"`.
- `README.md`: add a short "Figures" subsection under the tools/skills area describing: TikZ/pgfplots/tabular first; `save_figure(course, page_image, bbox, name)` with fractional bbox to embed a cropped drawing into `ExtFiles/`; prose last. If README lists the MCP tools, add `save_figure` to that list. If README shows `resolve_placement` args, add `subsection_hint`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest tests/test_version_bump.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json pyproject.toml README.md tests/test_version_bump.py
git commit -m "chore: bump to 0.2.0; document save_figure + figure workflow"
```

---

### Task 12: Full-suite + plugin validation gate

**Files:**
- None (verification only).

- [ ] **Step 1: Run the full test suite**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && python -m pytest -q`
Expected: all green (64 existing + the new tests). If any pre-existing test broke on the `subsection_block`/`_resolve_placement`/`DuplicateNoteError` signature changes, fix the CALLERS/tests to the new signatures (do not revert the design). Common spots: any existing test calling `subsection_block(title, body, date)` (now needs `section_title`), `_resolve_placement(a,b,c)` (now 4-arg), or asserting the old `DuplicateNoteError` message/`note:DATE`-only label.

- [ ] **Step 2: Validate the plugin**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && claude plugin validate . 2>&1 | tail -20`
Expected: clean (no errors). If `claude` CLI is unavailable, JSON-lint both manifests instead: `python -c "import json;[json.load(open(p)) for p in ['.claude-plugin/plugin.json','.claude-plugin/marketplace.json']];print('ok')"`.

- [ ] **Step 3: Smoke the MCP server over stdio**

Run: `cd ~/Desktop/Projects/ScribeTeX/.worktrees/fix-report-and-figures && PYTHONPATH=src python -c "import asyncio; from scribetex import server; print(sorted(asyncio.run(server.mcp.get_tools()).keys()) if hasattr(server.mcp,'get_tools') else 'n/a')" 2>/dev/null || PYTHONPATH=src python -c "import asyncio; from scribetex import server;
async def go():
    return sorted((await server.mcp.list_tools()), key=lambda t: t.name)
print([t.name for t in asyncio.run(go())])"`
Expected: lists `prepare_note`, `resolve_placement`, `save_figure`, `write_section`.

- [ ] **Step 4: Commit any fixups**

```bash
git add -A && git commit -m "test: fix callers for new signatures; full suite green" || echo "nothing to fix up"
```

---

## Self-Review

- **Spec coverage:** §1.2→T2, §1.3→T2, §3.1→T1, §2.2→T3+T4, §2.3→T5, pgfplots→T6, save_figure crop→T7+T8, brief→T9, §5.1/§5.2→T10, version bump→T11, §1.1→resolved by T11 version bump (fresh cache). All spec items mapped.
- **Placeholder scan:** every code step has real code; no TBDs.
- **Type consistency:** `subsection_block` is 4-arg (T3) and every caller updated (T4); `_resolve_placement`/`resolve_placement` are 4-arg (T5) and the schema test asserts it (T10); `DuplicateNoteError` 3-arg ctor (T4). `note_key`/`note_slug` defined in T3, consumed in T4/T5/T7-none (figures uses its own slug). `crop_to_extfiles` signature consistent T7↔T8. Version string `0.2.0` consistent across T11 files and its test.
