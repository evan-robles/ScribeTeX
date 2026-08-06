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
