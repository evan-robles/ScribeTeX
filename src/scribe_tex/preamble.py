r"""Canonical LaTeX preamble for a scribe-tex course document.

Adapted from the user's provided preamble: subfiles/bibresource wiring removed
so each course compiles as a standalone main.tex. The fancy header footer name
and course number are template placeholders.

Braces are doubled ({{ }}) so str.format substitutes ONLY {footer_name} and
{course_number}.
"""

# NOTE: every literal LaTeX brace below is doubled for str.format safety.
PREAMBLE_BODY = r"""\documentclass[11pt]{{article}}
\usepackage[margin=1in]{{geometry}}
\usepackage{{csquotes}}
\usepackage{{fancyhdr}}
\usepackage{{marginnote}}
\usepackage{{enumitem}}
\usepackage{{scrextend}}
\usepackage[bottom]{{footmisc}}
\usepackage{{siunitx}}
\usepackage{{tikz,graphicx}}
\usepackage{{float,subcaption}}
\usepackage{{booktabs,multirow}}
\usepackage{{amsmath,amssymb,amsthm}}
\usepackage{{bm,physics,mathtools,empheq}}
\usepackage[T1]{{fontenc}}
\usepackage{{mhchem}}
\usepackage[colorlinks,allcolors=black,urlcolor=cyan]{{hyperref}}

\MakeOuterQuote{{"}}

\fancypagestyle{{main}}{{
    \fancyhf{{}}
    \fancyhead[L]{{\leftmark}}
    \fancyhead[R]{{{course_number}}}
    \fancyfoot[R]{{{footer_name}\ \thepage}}
}}
\fancypagestyle{{plain}}{{
    \fancyhead{{}}
    \renewcommand{{\headrulewidth}}{{0pt}}
}}

\reversemarginpar

\setitemize[3]{{label={{\scriptsize$\blacksquare$}}}}

\deffootnotemark{{\textsuperscript{{\textup{{[}}\thefootnotemark\textup{{]}}}}}}
\deffootnote[1.8em]{{0em}}{{0em}}{{\textsuperscript{{\thefootnote}}}}

\sisetup{{range-phrase=-,range-units=single}}

\usetikzlibrary{{fpu,shapes,angles,decorations.markings,decorations.pathmorphing}}
\colorlet{{rex}}{{red!80!black!90!orange!80}}
\colorlet{{blx}}{{blue!90!green!80}}
\definecolor{{DeepCerulean}}{{HTML}}{{006fb3}}
\colorlet{{grx}}{{green!50!black}}
\colorlet{{pux}}{{red!50!blue}}

\newcommand{{\kB}}{{k_\text{{B}}}}
\newcommand{{\lB}}{{\ell_\text{{B}}}}
\newcommand{{\Tg}}{{T_\text{{g}}}}
\newcommand{{\Tm}}{{T_\text{{m}}}}
\newcommand{{\Tc}}{{T_\text{{c}}}}
\newcommand{{\Mn}}{{M_\text{{n}}}}
\newcommand{{\Mw}}{{M_\text{{w}}}}
\newcommand{{\R}}{{\mathbb{{R}}}}
\newcommand{{\pKa}}{{\text{{p}}K_\text{{a}}}}
\newcommand{{\pH}}{{\text{{pH}}}}
\newcommand{{\e}}[1][]{{\text{{e}}^{{#1}}}}
\newcommand{{\prb}}[1]{{\left\langle{{#1}}\right\rangle}}
\newcommand{{\Dstroke}}{{\tikz{{
    \node[inner sep=0pt]{{$D$}};
    \draw (-0.1,0) -- ++(0.12,0);
}}}}
"""

ALLOWED_PACKAGES = [
    "geometry", "csquotes", "fancyhdr", "marginnote", "enumitem", "scrextend",
    "footmisc", "siunitx", "tikz", "graphicx", "float", "subcaption",
    "booktabs", "multirow", "amsmath", "amssymb", "amsthm", "bm", "physics",
    "mathtools", "empheq", "fontenc", "mhchem", "hyperref",
]

ALLOWED_MACROS = [
    r"\kB", r"\lB", r"\Tg", r"\Tm", r"\Tc", r"\Mn", r"\Mw", r"\R", r"\pKa",
    r"\pH", r"\e", r"\prb", r"\Dstroke",
]


def render_preamble(footer_name: str, course_number: str) -> str:
    """Fill the footer name and course number into the preamble template."""
    return PREAMBLE_BODY.format(footer_name=footer_name, course_number=course_number)
