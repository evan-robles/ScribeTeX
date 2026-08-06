r"""Canonical LaTeX preamble for a ScribeTeX course document.

This is the user's full preamble, used verbatim for every scaffolded course.
It is self-contained for a standalone per-course folder: the bibliography
resource is a local ``main.bib`` and ``\graphicspath`` points at a local
``ExtFiles/`` directory, both created by the scaffold step alongside main.tex.

The fancy-header course number and footer name are the only template fields.
Every other literal LaTeX brace is doubled ({{ }}) so ``str.format`` substitutes
ONLY {course_number} and {footer_name}.

Note: this preamble loads biblatex with ``backend=biber``; compiling a course
document therefore uses biber for the bibliography.
"""

# NOTE: every literal LaTeX brace below is doubled for str.format safety.
PREAMBLE_BODY = r"""\documentclass[11pt]{{article}}
\usepackage[margin=1in]{{geometry}}
\usepackage[T1]{{fontenc}}
\usepackage{{amsmath,amssymb,amsthm}}
\usepackage{{mathtools}}
\usepackage{{empheq}}
\usepackage{{bm}}
\usepackage{{physics}}
\usepackage{{mhchem}}
\usepackage{{siunitx}}
\usepackage{{graphicx}}
\usepackage{{tikz}}
\usetikzlibrary{{
    fpu,
    shapes,
    angles,
    decorations.markings,
    decorations.pathmorphing
}}

\usepackage{{float}}
\usepackage{{braket}}
\usepackage{{subcaption}}
\usepackage{{booktabs}}
\usepackage{{multirow}}
\usepackage{{csquotes}}
\usepackage{{enumitem}}
\usepackage{{marginnote}}
\usepackage{{scrextend}}
\usepackage[bottom]{{footmisc}}
\usepackage{{fancyhdr}}


\usepackage[
    backend=biber,
    style=apa
]{{biblatex}}

\addbibresource{{main.bib}}
\usepackage{{xr}}
\usepackage{{subfiles}}
\usepackage[
    colorlinks,
    allcolors=black,
    urlcolor=cyan
]{{hyperref}}


\MakeOuterQuote{{"}}


\fancypagestyle{{main}}{{
    \fancyhf{{}}
    \fancyhead[L]{{\leftmark}}
    \fancyhead[R]{{{course_number}}}
    \fancyfoot[R]{{{footer_name}\ \thepage}}
}}

\fancypagestyle{{plain}}{{
    \fancyhf{{}}
    \renewcommand{{\headrulewidth}}{{0pt}}
}}

\pagestyle{{main}}

\reversemarginpar

\setitemize[3]{{label={{\scriptsize$\blacksquare$}}}}

\setitemize[4]{{label={{
\tikz[
scale=0.06,
baseline={{(0,-0.14)}}
]{{
\draw[line width=0.3pt]
(0,1)--(1.2,0)--(0,-1)--(3.5,0)--cycle;
\fill
(1.2,0)--(0,-1)--(3.5,0);
}}
}}}}



\deffootnotemark{{
\textsuperscript{{\textup{{[}}\thefootnotemark\textup{{]}}}}
}}

\deffootnote[1.8em]{{0em}}{{0em}}{{
\textsuperscript{{\thefootnote}}
}}


\DefineBibliographyStrings{{english}}{{
    bibliography={{References}}
}}



\sisetup{{
    range-phrase=-,
    range-units=single
}}


\colorlet{{rex}}{{red!80!black!90!orange!80}}
\colorlet{{blx}}{{blue!90!green!80}}
\definecolor{{DeepCerulean}}{{HTML}}{{006FB3}}
\colorlet{{grx}}{{green!50!black}}
\colorlet{{pux}}{{red!50!blue}}


\graphicspath{{{{ExtFiles/}}}}


\newcommand{{\kB}}{{k_{{\mathrm B}}}}
\newcommand{{\lB}}{{\ell_{{\mathrm B}}}}
\newcommand{{\Tg}}{{T_{{\mathrm g}}}}
\newcommand{{\Tm}}{{T_{{\mathrm m}}}}
\newcommand{{\Tc}}{{T_{{\mathrm c}}}}
\newcommand{{\Mn}}{{M_{{\mathrm n}}}}
\newcommand{{\Mw}}{{M_{{\mathrm w}}}}
\newcommand{{\R}}{{\mathbb{{R}}}}
\newcommand{{\pKa}}{{\mathrm{{p}}K_{{\mathrm a}}}}
\newcommand{{\pH}}{{\mathrm{{pH}}}}
\newcommand{{\ee}}{{\mathrm e}}

\newcommand{{\Dstroke}}{{
\tikz{{
\node[inner sep=0pt]{{$D$}};
\draw(-0.1,0)--++(0.12,0);
}}
}}

\newcommand{{\asym}}[2]{{\braket{{#1 || #2}}}}
\newcommand{{\chemint}}[2]{{(#1\,|\,#2)}}
"""

ALLOWED_PACKAGES = [
    "geometry", "fontenc", "amsmath", "amssymb", "amsthm", "mathtools",
    "empheq", "bm", "physics", "mhchem", "siunitx", "graphicx", "tikz",
    "float", "braket", "subcaption", "booktabs", "multirow", "csquotes",
    "enumitem", "marginnote", "scrextend", "footmisc", "fancyhdr", "biblatex",
    "xr", "subfiles", "hyperref",
]

ALLOWED_MACROS = [
    r"\kB", r"\lB", r"\Tg", r"\Tm", r"\Tc", r"\Mn", r"\Mw", r"\R", r"\pKa",
    r"\pH", r"\ee", r"\Dstroke", r"\asym", r"\chemint",
]


def render_preamble(footer_name: str, course_number: str) -> str:
    """Fill the footer name and course number into the preamble template."""
    return PREAMBLE_BODY.format(footer_name=footer_name, course_number=course_number)
