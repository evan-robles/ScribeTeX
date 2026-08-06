"""Create a new per-course LaTeX document (topic-based, full title page)."""
from __future__ import annotations
from pathlib import Path

from .preamble import render_preamble
from .placement import ENTRIES_START, ENTRIES_END
from .classify import course_slug

DEFAULT_FOOTER_NAME = "Robles"
DEFAULT_AUTHOR = "Evan S. Robles"
DEFAULT_AFFILIATION = "University of Chicago"


def build_main_tex(course_name: str, course_number: str,
                   author: str = DEFAULT_AUTHOR,
                   affiliation: str = DEFAULT_AFFILIATION,
                   footer_name: str = DEFAULT_FOOTER_NAME) -> str:
    """Full standalone document matching the canonical template: preamble, a
    titlepage (course name + number + author + affiliation), a plain-styled
    table of contents, and an empty topic-section ENTRIES region."""
    preamble = render_preamble(footer_name=footer_name, course_number=course_number)
    return (
        preamble
        + "\n\\begin{document}\n\n"
        + "\\begin{titlepage}\n"
        + "    \\thispagestyle{empty}\n\n"
        + "    \\centering\n\n"
        + "    \\vspace*{2cm}\n\n"
        + f"    {{\\Huge\\bfseries {course_name}\\par}}\n\n"
        + "    \\vspace{0.5cm}\n\n"
        + f"    {{\\Large {course_number}\\par}}\n\n"
        + "    \\vspace{0.8cm}\n\n"
        + "    \\rule{0.6\\textwidth}{0.6pt}\n\n"
        + "    \\vspace{0.8cm}\n\n"
        + f"    {{\\Large {author}\\par}}\n\n"
        + "    \\vspace{0.3cm}\n\n"
        + "    {\\large \\today \\par}\n\n"
        + "    \\vfill\n\n"
        + "    \\textit{\n"
        + f"    {affiliation}\n"
        + "    }\n\n"
        + "\\end{titlepage}\n"
        + "\\newpage\n\n"
        + "\\tableofcontents\n"
        + "\\thispagestyle{plain}\n"
        + "\\newpage\n\n"
        + f"{ENTRIES_START}\n{ENTRIES_END}\n"
        + "\\end{document}\n"
    )


def scaffold_course(root: Path, course_name: str, course_number: str,
                    author: str = DEFAULT_AUTHOR,
                    affiliation: str = DEFAULT_AFFILIATION,
                    footer_name: str = DEFAULT_FOOTER_NAME) -> Path:
    """Create a new course folder with main.tex plus the sidecar files its
    preamble references (an empty main.bib for biblatex, and an ExtFiles/
    directory for \\graphicspath), so the document compiles standalone."""
    course_dir = root / course_slug(course_name)
    main_tex = course_dir / "main.tex"
    if main_tex.exists():
        raise FileExistsError(main_tex)
    course_dir.mkdir(parents=True, exist_ok=True)
    main_tex.write_text(
        build_main_tex(course_name, course_number, author, affiliation, footer_name),
        encoding="utf-8",
    )
    # Sidecars required by the preamble.
    bib = course_dir / "main.bib"
    if not bib.exists():
        bib.write_text(
            "% Bibliography for this course. Add BibLaTeX entries here.\n",
            encoding="utf-8",
        )
    (course_dir / "ExtFiles").mkdir(exist_ok=True)
    return main_tex
