---
name: new-course
description: Scaffold a new per-course LaTeX document with the standard title page, preamble, and bibliography/graphics sidecars, ready for notes.
category: general
---

# New Course

## Goal
Create a fresh course document under the notes root, using the canonical
template: a full title page (course name + number + author + affiliation), a
table of contents, the shared preamble, and the empty topic-section region — plus
the `main.bib` and `ExtFiles/` sidecars so it compiles standalone. Use this to
set a course up front; note that `process-note` scaffolds automatically on first
use, so this skill is optional.

## Instructions

Run the scaffold script with the course name and number:

```bash
python skills/new-course/scripts/run.py --name "<Course Name>" --number "DEPT 10100"
```

Optional flags override the defaults `--author "Evan S. Robles"` and
`--affiliation "University of Chicago"`. The script prints JSON with the created
`main_tex` path (or an error if the course already exists — it never overwrites).

The document is written to `<notes-root>/<Course-Slug>/main.tex`, where the notes
root is `~/Desktop/College/Notes` by default (override with the
`SCRIBE_TEX_NOTES_ROOT` environment variable).

## Examples

Scaffold a course with a custom author:
```bash
python skills/new-course/scripts/run.py --name "<Course Name>" --number "DEPT 20200" --author "Evan S. Robles"
```

## Constraints
- **Environment**: requires the `scribe_tex` package importable (plugin sets
  PYTHONPATH; the SessionStart hook installs deps).
- **No overwrite**: refuses if `main.tex` already exists for that course.
- **Write-only**: does not compile the document; use `compile-course` for a PDF.

---

**Author:** Evan S. Robles
**Contact:** [GitHub @evan-robles](https://github.com/evan-robles)
