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
