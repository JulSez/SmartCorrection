import unittest

from moteur.render import latex_escape_plain_text


class PlainTextLatexTests(unittest.TestCase):
    def test_reserved_characters_are_escaped_before_generated_math(self):
        text = latex_escape_plain_text(r'50% & $x_1$ {test} \sqrt{6} ; − × √ ≤ ≥ ≠ → ⇔ ∞')
        self.assertIn(r'50\% \& \$x\_1\$ \{test\} \textbackslash{}sqrt\{6\}', text)
        for command in ('times', 'sqrt', 'leq', 'geq', 'neq', 'rightarrow', 'Leftrightarrow', 'infty'):
            self.assertIn('\\'+command, text)
        self.assertNotIn('−', text)
        self.assertNotIn(r'\textbackslash{}times', text)

    def test_accents_zero_and_unavailable_glyphs(self):
        self.assertEqual(latex_escape_plain_text('e\u0301lève'), 'élève')
        self.assertEqual(latex_escape_plain_text(0), '0')
        self.assertEqual(latex_escape_plain_text(None), '')
        self.assertEqual(latex_escape_plain_text('🙂'), r'\texttt{[U+1F642]}')
        self.assertEqual(latex_escape_plain_text('x\u202f=\u00a0−2\r\n'), r'x~=~-2\newline{}')
