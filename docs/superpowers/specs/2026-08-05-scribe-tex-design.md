# scribe-tex — Design Specification

**Date:** 2026-08-05
**Status:** Approved (pending written-spec review)
**Project location:** `~/Desktop/Projects/scribe-tex/`

---

## Problem

Evan takes class notes by hand on an iPad (Apple Pencil). He wants those notes
turned into polished, typeset LaTeX — organized so that each **course** has its
own document and each **class date** becomes its own dated section, matching the
Steven Labalme compiled-course-notes aesthetic (title page → "Topics" table of
contents → dated sections), using a specific LaTeX preamble he provided.

The manual path today is: export a note from the iPad as a PDF/image, then
hand-transcribe the handwriting and math into LaTeX and paste it into the right
file at the right place. This is slow and error-prone, and getting placement
(which course, which date, insertion order) right by hand is tedious.

**Goal:** an app that ingests a handwritten note export, transcribes it to LaTeX
via a vision model, and files it into the correct per-course document as a
correctly-ordered dated section — with the user confirming placement before
anything is written.

## Inputs & Outputs

- **Input:** a filesystem path to a handwritten note export (PDF or image)
  produced by the iPad. (Future: a OneNote page reference — see NoteSource seam.)
- **Output:** an updated (or newly scaffolded) per-course `main.tex` under the
  notes root, with the transcribed note inserted as a dated `\section`. Write-only
  — no PDF compilation is performed by the app.

## Non-goals (v1)

- No PDF/LaTeX compilation (the user compiles in their own editor workflow).
- No OneNote integration implemented (only the pluggable seam is built — see
  "OneNote investigation" below for why).
- No GitHub Pages site. The GitHub repo ships with a README as documentation.
- No standalone web UI. The interface is a FastMCP server driven by an agent.

---

## Key decisions (from brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Input format | Handwritten PDF/image | That's what the iPad exports. |
| Transcription | **Agent-delegated** (Approach B) | The calling agent (Claude Code) is already a top-tier vision model; keeps the server offline, key-free, and unit-testable. |
| Course/date detection | **Infer, then confirm** | App detects course/date/target and waits for user approval before writing — safest placement. |
| Course storage | **One repo per course, auto-scaffolded** | First time a course is seen, scaffold a full `main.tex` (preamble + title + Topics TOC); later notes append sections. |
| File granularity | **All sections in one `main.tex`** | Simpler than subfiles-per-date; one file per course. |
| Duplicate dates | **Insert in date order; warn on dupes** | No silent overwrites; user chooses replace/append/skip. |
| Compilation | **Write only** | Keeps the server dependency-free (no TeX install). |
| Notes root | `~/Desktop/College/Notes` | Dedicated folder under existing College dir. |
| Input extensibility | **Pluggable `NoteSource` seam** | Lets a OneNote image-fetch source drop in later without touching placement logic. |
| Repo | `scribe-tex`, local git only, README docs, no Pages | Matches user's existing project style. |

---

## OneNote investigation (why it is future-only)

A deep dive into the Microsoft Graph OneNote API established:

- The API exposes notebooks/sections/pages and returns page content as **"output
  HTML"** whose documented element set is text, headings, lists, tables, `<img>`,
  `<object>`, `<iframe>` — **no ink / drawing / InkML / stroke element**.
- There is **no handwriting-recognition / ink-to-text** exposed anywhere in the
  API. Apple Pencil strokes do not come through as text or as strokes.
- Sources:
  - https://learn.microsoft.com/en-us/graph/api/resources/onenote-api-overview
  - https://learn.microsoft.com/en-us/graph/onenote-get-content
  - https://learn.microsoft.com/en-us/graph/onenote-input-output-html

**Silver lining:** the API *can* return page images (`/preview` and the
`data-fullres-src` resource endpoints, `GET /me/onenote/resources/{id}/$value`).
So a future `OneNoteSource` could **replace the manual export step** by fetching
page PNGs directly — but transcription would still be done by the vision agent on
those images. OneNote is therefore an *image-fetching convenience*, never a text
source. This is exactly why the input layer is abstracted behind `NoteSource`:
the future source only needs to produce page PNGs; nothing downstream changes.

---

## Architecture & data flow

The **calling agent** performs the single AI step (vision transcription). The
**server** is pure, offline, and deterministic everywhere else — so all risky
logic (date-ordered insertion, duplicate detection, scaffolding) is unit-testable
with no network dependency and no API keys.

### The `NoteSource` seam

```python
class NoteSource(Protocol):
    def fetch_pages(self, ref: str) -> list[Path]:
        """Return page images (PNG paths) for the given source reference."""
```

- **`FileSource`** (v1): `ref` is a path to a PDF/image; renders each page to a
  PNG via PyMuPDF.
- **`OneNoteSource`** (v1 stub): raises `NotImplementedError` with a docstring
  describing the future Graph `/preview` + `data-fullres-src` path.

A small registry maps `source` strings ("file", "onenote") to implementations so
`prepare_note(source=...)` selects the right one.

### Flow for processing one note

1. User: *"process ~/Downloads/linalg-oct3.pdf"*.
2. Agent → **`prepare_note(source="file", ref=path)`**. Server selects the
   NoteSource, renders page PNGs, returns image paths + a transcription brief
   (allowed macros/packages from the preamble, house style, instruction to
   extract a course hint and the class date) + the list of known courses.
3. Agent reads the PNGs, transcribes handwriting + math to LaTeX, and infers the
   course + date.
4. Agent → **`resolve_placement(course_hint, date)`**. Server fuzzy-matches the
   hint to an existing course repo (or flags it new), normalizes the date, and
   reports the target path, insertion point, and duplicate status.
5. Agent shows the user: detected course, date, target path, new-vs-existing,
   duplicate status → **user confirms** (this is the "infer, then confirm" gate,
   happening naturally in chat).
6. Agent → **`write_section(course, date, latex_body, on_duplicate)`**. Server
   scaffolds the repo if new, inserts the section in date order, applies the
   duplicate policy, writes `main.tex`, and returns a diff summary.

Steps 2, 4, and 6 are deterministic and unit-tested. Step 3 (AI) lives in the
agent.

---

## Module layout

```
scribe-tex/
├── pyproject.toml               # deps: fastmcp, pymupdf, python-dateutil; dev: pytest
├── README.md                    # documentation (no GitHub Pages)
├── src/scribe_tex/
│   ├── server.py                # FastMCP: the 3 tools; thin, delegates to modules
│   ├── sources/
│   │   ├── base.py              # NoteSource Protocol + registry (register/get_source)
│   │   ├── file_source.py       # FileSource: PDF/image -> page PNGs (PyMuPDF)
│   │   └── onenote_source.py    # stub (NotImplementedError); documents future Graph path
│   ├── transcription_brief.py   # builds the brief handed to the agent
│   ├── preamble.py              # canonical preamble template + macro/package inventory
│   ├── classify.py              # fuzzy course-hint -> repo match; date parsing/normalization
│   ├── scaffold.py              # create a new course repo (preamble + title + Topics TOC)
│   ├── placement.py             # PURE: insertion point, date ordering, duplicate detection
│   ├── writer.py                # apply placement to main.tex; return a diff summary
│   └── config.py                # NOTES_ROOT resolution (default ~/Desktop/College/Notes)
└── tests/
    ├── fixtures/                # tiny sample PDFs, a pre-built course main.tex
    ├── test_placement.py        # date-order insert, dupe warn, first-section, out-of-order
    ├── test_scaffold.py         # new-repo structure shape
    ├── test_classify.py         # hint matching + date parsing edge cases
    └── test_writer.py           # idempotency, diff correctness
```

### Responsibility one-liners

- **`server.py`** — MCP surface only; validates args, calls one module each. No
  business logic.
- **`sources/`** — the seam; `base.py` holds the Protocol + registry.
- **`preamble.py`** — single source of truth for the template; exposes the
  macro/package inventory so the brief's "allowed macros" never drifts from the
  real preamble.
- **`placement.py`** — pure crown-jewel module: given existing section dates + a
  new date, returns `insert_at` / `is_duplicate`. Zero I/O; exhaustively tested.
- **`scaffold.py` vs `writer.py`** — scaffold creates a new course from nothing;
  writer edits an existing `main.tex`. Split to keep each focused.

---

## Tool contracts

### `prepare_note(source: str = "file", ref: str) -> dict`

Selects the NoteSource, renders pages to PNGs in a temp dir, returns:

```json
{
  "page_images": ["/tmp/.../p1.png", "..."],
  "brief": "Transcribe to LaTeX using ONLY these packages/macros: <inventory>. House style: <rules>. Also extract: course name/number hint, and the class date (look for a written date header).",
  "notes_root": "/Users/evane/Desktop/College/Notes",
  "known_courses": ["MATH 257 Linear Algebra", "CHEM 20100 Inorganic Chemistry I"]
}
```

`known_courses` primes the agent's course inference against repos that already
exist.

### `resolve_placement(course_hint: str, date: str) -> dict`

Fuzzy-matches `course_hint` to an existing repo; normalizes `date` (accepts
"Oct 3 2025", "10/3/25", "2025-10-03" → ISO). Returns:

```json
{
  "course": "MATH 257 Linear Algebra",
  "course_status": "existing",
  "target_path": ".../Notes/MATH-257-Linear-Algebra/main.tex",
  "date_iso": "2025-10-03",
  "date_display": "October 3, 2025",
  "insert_position": "after section dated 2025-09-28",
  "duplicate": false,
  "match_confidence": "high"
}
```

`course_status` is `"existing"` or `"new"`; `match_confidence` is `"high"` or
`"low"`. Low confidence or `new` → the agent is instructed to ask the user rather
than assume.

### `write_section(course: str, date: str, latex_body: str, on_duplicate: str = "warn") -> dict`

`on_duplicate` ∈ {`"warn"`, `"replace"`, `"append"`}, default `"warn"`.
Scaffolds the repo if new, inserts the `\section` in date order, applies the
duplicate policy (default `warn` = refuse + report), writes `main.tex`. Returns:

```json
{
  "written": true,
  "target_path": ".../main.tex",
  "diff_summary": "+42 lines, section inserted after 2025-09-28",
  "compiled": false
}
```

---

## `main.tex` format

A scaffolded course document contains the user's preamble, a title page, a
"Topics" heading, and an entries region delimited by explicit markers so the
writer never has to guess where the body is:

```latex
% ... user's preamble ...
\begin{document}
% ... title page + \tableofcontents ("Topics") ...

% >>> ENTRIES
% <<< ENTRIES
\end{document}
```

Each class date is inserted between the markers as:

```latex
\section{October 3, 2025}
\label{sec:2025-10-03}
% --- begin transcribed body ---
<agent's LaTeX>
% --- end transcribed body ---
```

The ISO `\label` (`sec:YYYY-MM-DD`) is the machine anchor `placement.py` reads to
enumerate existing dates and detect duplicates — robust against the
human-readable `\section` title. Insertion keeps sections in ascending date
order.

### Preamble adaptation

The provided preamble uses a `subfiles`-based master layout (`\subfix{../main.bib}`,
`\graphicspath{{../ExtFiles/}}`, a `main` fancy page style with a `Labalme`
footer and a hardcoded course number `3.942`). Since v1 uses a single standalone
`main.tex` per course (no subfiles), the scaffold step adapts the preamble:

- Drop/neutralize the `subfiles` wiring so the file compiles standalone.
- Make the fancy-header footer name and course number **template variables**
  filled from the course (footer name defaults to the user's surname; course
  number/label from the course identity), rather than hardcoded `Labalme` /
  `3.942`.
- Keep all math/formatting packages and custom macros (`\R`, `\prb`, `\e`,
  `\Dstroke`, etc.) intact — these are the "allowed macros" the brief advertises.

Exact preamble-adaptation details are finalized in the implementation plan.

---

## Error handling

- **Unreadable/missing input file** → `prepare_note` returns a structured error;
  agent reports it, does not proceed.
- **Unparseable date** → `resolve_placement` returns `match_confidence:"low"` and
  a message; agent asks the user for the date.
- **Ambiguous / low-confidence course** or **new course** → agent must confirm
  the course (and, if new, the exact folder name) with the user before
  `write_section`.
- **Duplicate date** with default `on_duplicate:"warn"` → `write_section` refuses
  and reports the conflict; agent asks the user to choose replace/append/skip.
- **Corrupt/partial `main.tex`** (missing ENTRIES markers) → writer refuses to
  edit and reports, rather than risk mangling the file.

---

## Testing strategy

- **`placement.py`** is the priority: pure functions, exhaustive unit tests
  (empty doc / first section, insert-before-all, insert-between, insert-after-all,
  exact-duplicate, same-day-different-content).
- **`classify.py`**: date-format matrix (`"Oct 3 2025"`, `"10/3/25"`,
  `"2025-10-03"`, ambiguous `"3/4"`); course fuzzy-match hits and misses.
- **`scaffold.py`**: a fresh course produces a `main.tex` with preamble, title,
  Topics, and ENTRIES markers present and well-formed.
- **`writer.py`**: idempotency (re-inserting the same section is a no-op under
  `warn`), diff-summary correctness, marker integrity preserved.
- **`file_source.py`**: a tiny fixture PDF renders the expected number of PNGs.
- Transcription (the AI step) is out of scope for automated tests — it lives in
  the agent.

---

## Reproducibility & config

- `NOTES_ROOT` resolves from an env var, falling back to
  `~/Desktop/College/Notes`. Surfaced in `prepare_note` output so the agent
  always reports where files will land.
- No secrets, no network calls in v1 — the server is fully offline and
  deterministic.

---

## Limitations

- Transcription accuracy depends entirely on the calling vision agent; the app
  makes no accuracy guarantees and does no automated verification of the LaTeX
  against the source image.
- No compilation: a transcription that produces invalid LaTeX is caught only when
  the user compiles. (Acceptable per the write-only decision.)
- OneNote is not implemented — only the seam exists.
- Single-document-per-course means a term's `main.tex` grows over time; this was
  chosen for simplicity over subfiles.
