# ScribeTeX — field-report fixes + figures feature (design)

**Date:** 2026-08-06
**Author:** Evan S. Robles

## Context

A real end-to-end run (recorded in the plugin cache's `SUGGESTIONS.md`, tested
against the stale `scribetex/0.1.0` cache) surfaced blockers and design issues.
Verified against current repo source (`master`, `4864cb4`), the findings triage
as follows:

- **§1.1** `prepare_note` missing `ref` — **already fixed** in current source
  (`server.py` `prepare_note(source, ref)`). The tester ran an old cached
  checkout. A version bump forces a fresh cache on reinstall.
- **§1.2** `run.py` cannot import `scribetex` without external PYTHONPATH — real.
- **§1.3** SKILL.md command doubles the base path — real.
- **§3.1** empty-value error strings — real.
- **§2.2 / §2.3** duplicate detection is date-only, so two different-topic notes
  from the same day collide, and `resolve_placement` / `write_section` use
  different keys — real.

Plus a new feature request: figures/drawings. Charts, tables, graphs → TikZ /
pgfplots / tabular; freehand drawings → embed a cropped image.

## Goals

1. Fix §1.2, §1.3, §3.1.
2. Re-key duplicate detection on `(date, section, subsection)` and align
   `resolve_placement` with `write_section` (§2.2/§2.3).
3. Add a figures capability: pgfplots in the preamble; a `save_figure` MCP tool
   that crops a rendered page region into `ExtFiles/`; a brief that enforces
   **TikZ/pgfplots/tabular → embed crop → prose**.
4. Add schema-shape and import smoke tests (§5.1/§5.2) plus dedup and crop tests.
5. Bump version `0.1.0 → 0.2.0` in `plugin.json`, `marketplace.json`,
   `pyproject.toml`.

## Non-goals

- No change to the write-only guarantee of the MCP server for LaTeX
  compilation (compile stays in the `compile-course` skill). `save_figure` is
  deterministic image I/O, not compilation.
- No marketplace/slug renaming (§4.1 is historical; canonical slug already set).

## Design

### A. Bug fixes

**§1.2 — self-locating `run.py` (all four skills).** Before
`from scribetex import ...`, prepend the repo/plugin `src` dir to `sys.path`:

```python
import sys, pathlib
SRC = pathlib.Path(__file__).resolve().parents[3] / "src"
if SRC.is_dir():
    sys.path.insert(0, str(SRC))
```

`parents[3]` because each script sits at
`<root>/skills/<name>/scripts/run.py` → `parents[3]` == `<root>`. Removes the
external-PYTHONPATH dependency entirely.

**§1.3 — SKILL.md command paths.** Every documented command becomes
`python scripts/run.py ...` (relative to the skill's own base dir), never
`python skills/<name>/scripts/run.py ...`.

**§3.1 — error strings in `FileSource.fetch_pages`.**
- empty/blank `ref` → `ValueError("no note path provided: pass ref=<path to PDF/image>")`
- missing file → `FileNotFoundError("file not found: <path>")`
- unsupported extension → `ValueError("unsupported extension '<ext>'; supported: pdf, png, jpg, jpeg, heic")`

### B. Duplicate detection re-key (§2.2/§2.3)

**Label format.** `\label{note:<date>:<section-slug>:<subsection-slug>}` where
each slug is a lowercase, hyphenated, ASCII-safe reduction of the title (reuse
the existing slug helper style from `classify.course_slug`, or a local
`_slugify`). Example: `\label{note:2026-08-06:muscles-and-movement:muscles}`.

**`placement.py`.**
- `note_key(date_iso, section_title, subsection_title) -> str` builds the
  composite key string (the part after `note:`).
- `existing_note_labels(main_tex) -> list[str]` returns full composite keys
  (regex widened from `\d{4}-\d{2}-\d{2}` to the composite pattern).
- `subsection_block(title, body, date_iso, section_title)` — now needs the
  section title to build the composite label. (Signature change; update all
  callers.)

**`writer.py`.**
- `insert_note(main_tex, section_title, subsection_title, body, date_iso,
  on_duplicate)` computes `note_key(...)` and checks membership in
  `existing_note_labels`. Only an exact composite match is a duplicate.
- `_replace_note` matches on the composite label.
- `DuplicateNoteError` carries section + subsection so the message names what
  collided: `"a note for section '<S>' / subsection '<Sub>' on <date> already
  exists"`.

**`server.py`.**
- `resolve_placement(course_hint, section_hint, subsection_hint, date)` — adds
  `subsection_hint`, computes the same `note_key`, and reports `duplicate` using
  the composite key. Now `resolve` predicts `write` exactly (§2.3).
- `write_section` passes `section_title` through to `insert_note` (already has
  it) — no new arg, but the composite label is now built from it.

### C. Figures feature

**Preamble (`preamble.py`).**
- Add `\usepackage{pgfplots}` and `\pgfplotsset{compat=1.18}` after the tikz
  block. (Doubled braces for `str.format`: `\pgfplotsset{{compat=1.18}}`.)
- Add `"pgfplots"` to `ALLOWED_PACKAGES`.
- `graphicx`, `tikz`, `booktabs`, `float`, `subcaption`, and
  `\graphicspath{{ExtFiles/}}` are already present — no change.

**`save_figure` MCP tool (`server.py`).**
`save_figure(course, page_image, bbox, name) -> dict`:
- `course`: course NAME (→ folder via `course_slug`); the crop lands in that
  course's `ExtFiles/`. The course dir must already exist (scaffold happens on
  the first `write_section`); if not, return an actionable error.
- `page_image`: absolute path to a page PNG previously returned by
  `prepare_note`.
- `bbox`: `[x0, y0, x1, y1]` as fractions in `[0,1]` of page width/height
  (origin top-left). Validate `0 <= x0 < x1 <= 1`, `0 <= y0 < y1 <= 1`.
- `name`: base filename (no extension); sanitized to `[A-Za-z0-9_-]`.
- Crops with Pillow (`PIL.Image`), converts fractions → pixels via the PNG's
  own dimensions, writes `ExtFiles/<name>.png`, returns
  `{"saved": true, "filename": "<name>.png", "path": "<abs>",
  "include": "\\includegraphics[width=…]{<name>}"}` (a ready `\includegraphics`
  snippet is convenience, not required).
- On error returns `{"saved": false, "error": ...}` naming the field + fix.
- Pillow is added as a dependency (`pillow>=10`).

**Brief rewrite (`transcription_brief.py`).** Replace the single "render
diagrams as prose" line with the fixed priority:

> For any chart, table, graph, plot, or other **data/structured** figure:
> reproduce it faithfully as TikZ / pgfplots / `tabular` (all loaded). If it
> cannot be faithfully reproduced that way, embed a cropped image of the region
> by calling the `save_figure` tool (page image + a `[x0,y0,x1,y1]` fractional
> bounding box) and `\includegraphics` the returned filename. Only if neither is
> possible, describe it in prose. Always tell the user which figures were drawn
> as TikZ, which were embedded as images, and which were described in prose.

Also document the fractional-bbox convention and `pgfplots` availability.

### D. Tests

- `test_schema.py`: each MCP tool (`prepare_note`, `resolve_placement`,
  `write_section`, `save_figure`) exposes its expected parameters (introspect
  the FastMCP tool schema). Catches §1.1-style drift.
- `test_import_smoke.py`: `import scribetex; from scribetex import server`.
- Dedup: two notes, same date, different section/subsection → both write, no
  false duplicate; same date+section+subsection → duplicate raised; replace
  collapses only the exact-key blocks.
- `resolve_placement` `duplicate` field agrees with a subsequent
  `write_section` outcome for the same composite key.
- `save_figure`: crops a fixture PNG to the expected pixel box; rejects an
  out-of-range bbox with a named error; sanitizes `name`.
- `run.py` self-location: importable with PYTHONPATH unset (subprocess test).

### E. Version bump

`0.1.0 → 0.2.0` in `.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json`, `pyproject.toml`.

## Reuse (do not reimplement)

`classify.course_slug` (slug style), `config.notes_root`, existing
`placement`/`writer` structure, `sources.file_source.FileSource` (add error
strings + reuse for `save_figure` page paths), `scaffold` (unchanged; already
makes `ExtFiles/`).

## Risks

- **Label migration:** existing course docs carry old date-only labels
  (`note:2026-08-06`). The widened regex must still *find* them (so an old note
  is recognized) while new notes use composite keys. Decision: the composite
  regex matches both — an old label simply has empty section/subsection segments
  → treated as its own key; it will not false-collide with new composite keys.
  No rewrite of existing docs.
- **Pillow dependency:** new dep; add to `pyproject.toml` and the bootstrap
  hook's import check.
- **save_figure course-dir precondition:** if called before the course is
  scaffolded, `ExtFiles/` doesn't exist. Return a clear error telling the
  caller to `write_section` first (which scaffolds), or create the dir on
  demand. Decision: create `ExtFiles/` on demand (idempotent, harmless), so the
  agent can save figures before the first write.

## Verification

- `pytest -q` green (64 existing + new).
- `claude plugin validate .` clean.
- Manual: run `save_figure` on a real rendered page; confirm the crop lands in
  `ExtFiles/` and `\includegraphics` resolves.
- Two-topic same-day note files as two subsections with no duplicate error.
