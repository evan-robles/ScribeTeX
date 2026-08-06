---
name: list-courses
description: List the existing course documents under the notes root, with each course's topic sections and note count.
category: general
---

# List Courses

## Goal
Give a quick inventory of the notes root: which courses exist, what topic
`\section`s each contains, and how many notes (subsections) have been filed. Use
this to see what's there before processing a new note, or to check placement.

## Instructions

Run the inventory script:

```bash
python scripts/run.py
```

It prints JSON: the `notes_root`, a `course_count`, and a `courses` array where
each entry has the course display name, its `main.tex` `path`, its `sections`
(top-level topic titles, in order), and a `note_count` (number of
note-labelled subsections). Reads `~/Desktop/College/Notes` by default (override
with `SCRIBETEX_NOTES_ROOT`).

## Examples

```bash
python scripts/run.py
```
Typical output shows each course with its topic sections (e.g.
`["Characterization Techniques", "Reaction Mechanisms"]`) and a note count.

## Constraints
- **Environment**: self-locating (prepends `../../../src` to `sys.path`); the
  SessionStart hook installs the `scribetex` package's deps.
- **Read-only**: this skill never modifies any document.

---

**Author:** Evan S. Robles
**Contact:** [GitHub @evan-robles](https://github.com/evan-robles)
