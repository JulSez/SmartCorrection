"""PR26: make wide displayed maths fit inside two-column corriges."""
from __future__ import annotations

import re

from . import pr18_patch as pr18

_BASE_APPLY_SOURCE_LAYOUT = pr18._apply_source_layout

_FIT_MACRO = r'''\newsavebox{\SCmathbox}
\newcommand{\SCfitmath}[1]{%
  \sbox{\SCmathbox}{$\displaystyle #1$}%
  \ifdim\wd\SCmathbox>\linewidth
    \resizebox{\linewidth}{!}{\usebox{\SCmathbox}}%
  \else
    \usebox{\SCmathbox}%
  \fi
}'''


def _fit_align_blocks(text: str) -> str:
    pattern = re.compile(r'\\begin\{align\*\}(.*?)\\end\{align\*\}', re.S)

    def repl(match):
        body = match.group(1).strip()
        # aligned keeps the original alignment points and line breaks, while
        # SCfitmath only shrinks the block when it actually exceeds the column.
        return '\\[\\SCfitmath{\\begin{aligned}' + body + '\\end{aligned}}\\]'

    return pattern.sub(repl, text)


def _apply_source_layout(source, layout):
    source = _BASE_APPLY_SOURCE_LAYOUT(source, layout)
    if layout['corrige']['columns'] != 2:
        return source

    # graphicx is part of the standard LaTeX installation and provides resizebox.
    if r'\usepackage{graphicx}' not in source:
        source = source.replace(r'\usepackage{xcolor}', r'\usepackage{xcolor}\usepackage{graphicx}', 1)
    if r'\newcommand{\SCfitmath}' not in source:
        source = source.replace(r'\begin{document}', _FIT_MACRO + '\n\\begin{document}', 1)

    start = source.find(r'\begin{multicols}{2}')
    end = source.find(r'\end{multicols}', start + 1)
    if start != -1 and end != -1:
        head = source[:start]
        middle = source[start:end]
        tail = source[end:]
        source = head + _fit_align_blocks(middle) + tail
    return source


# pr18._layout_renderer resolves this symbol dynamically from the pr18 module.
pr18._apply_source_layout = _apply_source_layout
