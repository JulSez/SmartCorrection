import unittest

from moteur import pr18_patch, pr26_patch  # noqa: F401


class DoubleColumnCorrigeTests(unittest.TestCase):
    def test_align_blocks_are_fitted_to_column_width(self):
        source = r'''\documentclass{article}
\usepackage{xcolor}
\begin{document}
\def\SCpanel{Corrigé}\setcounter{page}{1}
\begin{align*}
z&=\frac{3+i}{2-i}\\
&=\frac{(3+i)(2+i)}{(2-i)(2+i)}
\end{align*}
\end{document}'''
        layout = {
            'correction': {'size': 'A6', 'orientation': 'portrait', 'pages': 1},
            'corrige': {'size': 'A6', 'orientation': 'portrait', 'pages': 1, 'columns': 2},
            'assembly': 'cote-a-cote', 'print_format': 'auto',
        }
        rendered = pr18_patch._apply_source_layout(source, layout)
        self.assertIn(r'\usepackage{graphicx}', rendered)
        self.assertIn(r'\newcommand{\SCfitmath}', rendered)
        self.assertIn(r'\SCfitmath{\begin{aligned}', rendered)
        self.assertNotIn(r'\begin{align*}', rendered)

    def test_one_column_is_unchanged_by_pr26(self):
        source = r'''\documentclass{article}\usepackage{xcolor}\begin{document}\begin{align*}x&=1\end{align*}\end{document}'''
        layout = {
            'correction': {'size': 'A6', 'orientation': 'portrait', 'pages': 1},
            'corrige': {'size': 'A6', 'orientation': 'portrait', 'pages': 1, 'columns': 1},
            'assembly': 'cote-a-cote', 'print_format': 'auto',
        }
        rendered = pr18_patch._apply_source_layout(source, layout)
        self.assertIn(r'\begin{align*}', rendered)
        self.assertNotIn(r'\SCfitmath', rendered)


if __name__ == '__main__':
    unittest.main()
