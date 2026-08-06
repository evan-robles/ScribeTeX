---
name: compile-course
description: Compile a course's main.tex to PDF using the pdflatex and biber toolchain the template requires.
category: general
---

# Compile Course

## Goal
Build a course document to PDF. The ScribeTeX template uses `biblatex` with the
`biber` backend, so a correct build is `pdflatex → biber → pdflatex → pdflatex`.
This skill is the ONE place ScribeTeX compiles LaTeX — the MCP server stays
write-only — so compilation is always an explicit, opt-in step.

## Instructions

Compile by course name (resolved under the notes root):

```bash
python scripts/run.py --course "<Course Name>"
```

Or point directly at a `main.tex`:

```bash
python scripts/run.py --path ~/Desktop/College/Notes/Organic-Chemistry/main.tex
```

The script prints JSON: on success, `compiled: true` and the `pdf` path; on
failure, the failed step and the last ~25 lines of the log. If `pdflatex` or
`biber` are not on PATH, it reports that clearly instead of failing obscurely.

## Examples

```bash
python scripts/run.py --course "<Course Name>"
```

## Constraints
- **Environment**: requires a local TeX distribution providing `pdflatex` and
  `biber` (MacTeX or TeX Live). The skill degrades gracefully with a clear
  message if either is missing.
- **Requires** the `scribetex` package's deps; the script self-locates by
  prepending `../../../src` to `sys.path`.
- **Overwrites** the course's `main.pdf` and TeX aux files in place.

## References
- Kime, P.; Wemheuer, M.; Lehman, P. *biblatex* and *biber* — the bibliography
  backend the template targets.

---

**Author:** Evan S. Robles
**Contact:** [GitHub @evan-robles](https://github.com/evan-robles)
