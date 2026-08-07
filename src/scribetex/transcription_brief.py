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
        "- Produce the BODY ONLY. Do NOT include a preamble, \\documentclass, "
        "or \\begin{document}/\\end{document}.\n"
        "- Do NOT write the \\section or \\label line; the server adds those.\n"
        "- Structure the note's content using \\subsection{...} (and lower) for "
        "each topic; the whole note is placed under ONE top-level section that "
        "the server adds.\n"
        "- Use $...$ for inline math and align/equation for display math.\n"
        "- Transcribe faithfully; never invent content not on the page.\n"
        "\n"
        "FIGURES — CROP THE ORIGINAL BY DEFAULT. Any drawing, sketch, diagram, "
        "illustration, or labelled figure (anatomical, biological, schematic, "
        "freehand, flowchart — anything whose exact appearance matters) MUST be "
        "embedded as a cropped image of the real page, NEVER redrawn:\n"
        "  1. DEFAULT — embed a cropped image: call the save_figure tool with the "
        "page image path and a bounding box [x0, y0, x1, y1] as fractions in "
        "[0,1] of the page (origin top-left), then "
        "\\includegraphics{<returned filename>}.\n"
        "  2. TikZ / pgfplots is allowed ONLY for a genuine DATA chart — a bar, "
        "line, or scatter plot with clearly recoverable numeric values. tabular "
        "(booktabs) ONLY for a grid-like data TABLE. If it is not clearly one of "
        "these, treat it as a drawing and crop it (rule 1).\n"
        "  3. Prose only as a last resort, when a region genuinely cannot be "
        "cropped.\n"
        "  NEVER reconstruct or invent a hand-drawn diagram as TikZ from "
        "imagination — reproducing a sketch by guessing its geometry "
        "misrepresents the note. When in doubt, crop the original.\n"
        "  Tell the user which figures were embedded as cropped images, drawn as "
        "TikZ (data charts only), or described in prose.\n"
        "\n"
        f"- You MAY rely on these already-loaded packages: {packages}.\n"
        f"- You MAY use these predefined macros: {macros}.\n"
        "- \\ce{{...}} (mhchem) is available for chemistry formulae and reactions.\n"
        "\n"
        "ALSO EXTRACT (report separately, not inside the LaTeX):\n"
        "- course: the course name/number hint (from a header or the content).\n"
        "- section: a top-level SECTION title naming the note's overall theme "
        "(e.g. 'Characterization Techniques', 'Reaction Mechanisms'); the note "
        "is filed under this section.\n"
        "- subsection: a concise SUBSECTION title for this note's content.\n"
        "- date: the class date (look for a written date header).\n"
    )
