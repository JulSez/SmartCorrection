import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from pypdf import PdfReader, PdfWriter

from moteur.gui_prompts_v2 import make_prompt
from moteur.workflow_v2 import WorkflowApplication, reformat_pair_pdf


class WorkflowV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.app = WorkflowApplication(root/'db.sqlite', root/'data', root/'legacy')
        self.app.roster('TEST', 'nom;prenom\nAlpha;Alice\n', True)
        self.ident = self.app.create('TEST', 'Évaluation compacte')['id']
        writer = PdfWriter(); writer.add_blank_page(width=595, height=842)
        raw = io.BytesIO(); writer.write(raw)
        encoded = base64.b64encode(raw.getvalue()).decode()
        self.app.upload(self.ident, 'sujet', 'sujet.pdf', encoded)
        self.app.upload(self.ident, 'paquet', 'copies.pdf', encoded)

    def envelope(self, value):
        return dict(value, dossier=self.ident, revision=self.app.state(self.ident)['dossier']['revision'])

    def corriges(self):
        return self.envelope({'corriges': [
            {'version': 'A', 'sujet_latex': r'\textit{Sujet A}',
             'corrige_latex': r'\section*{Exercice 1}\begin{align*}x+1&=2\\x&=1\end{align*}'},
            {'version': 'B', 'sujet_latex': r'\textit{Sujet B}',
             'corrige_latex': r'\section*{Exercice 1}\begin{align*}x+2&=4\\x&=2\end{align*}'},
        ]})

    def test_formats_default_to_a6_and_are_in_prompts(self):
        self.assertEqual(self.app.state(self.ident)['formats'], {'correction': 'A6', 'corrige': 'A6'})
        self.app.save_formats(self.ident, 'A5', 'A4')
        self.assertEqual(self.app.state(self.ident)['formats'], {'correction': 'A5', 'corrige': 'A4'})
        prompt = make_prompt(self.app, self.ident, 'corriges')
        self.assertIn('A5 portrait', prompt)
        self.assertIn('A4 portrait', prompt)
        self.assertIn('TOUS les corrigés', prompt)

    def test_all_corriges_are_saved_before_grid_and_grid_reuses_them(self):
        text = json.dumps(self.corriges(), ensure_ascii=False)
        preview = self.app.exchange(self.ident, 'corriges', text, False)
        self.assertEqual([x['version'] for x in preview['corriges']], ['A', 'B'])
        self.assertFalse(self.app.state(self.ident)['corriges_valides'])
        self.app.exchange(self.ident, 'corriges', text, True)
        self.assertTrue(self.app.state(self.ident)['corriges_valides'])

        grid = self.envelope({'grilles': [
            {'nom': 'Grille A', 'version': 'A', 'exercices': [{'numero': '1', 'questions': [{'numero': '1', 'items': [
                {'code': 'A1', 'description': 'Résoudre', 'bareme_max': 1}
            ]}]}]},
            {'nom': 'Grille B', 'version': 'B', 'exercices': [{'numero': '1', 'questions': [{'numero': '1', 'items': [
                {'code': 'B1', 'description': 'Résoudre', 'bareme_max': 1}
            ]}]}]},
        ]})
        self.app.exchange(self.ident, 'grille', json.dumps(grid, ensure_ascii=False), True)
        state = self.app.state(self.ident)
        self.assertEqual(state['dossier']['revision'], 1)
        self.assertEqual([v['version'] for v in state['versions']], ['A', 'B'])
        self.assertTrue(all(v['corrige_latex'] for v in state['versions']))

    def test_pair_pdf_can_expand_correction_and_corrige_independently(self):
        pair = Path(self.temp.name)/'pair.pdf'
        writer = PdfWriter(); writer.add_blank_page(width=210*72/25.4, height=148*72/25.4); writer.write(str(pair)); writer.close()
        data = reformat_pair_pdf(pair, 'A5', 'A4')
        pdf = PdfReader(io.BytesIO(data))
        self.assertEqual(len(pdf.pages), 2)
        self.assertAlmostEqual(float(pdf.pages[0].mediabox.width), 148*72/25.4, places=2)
        self.assertAlmostEqual(float(pdf.pages[0].mediabox.height), 210*72/25.4, places=2)
        self.assertAlmostEqual(float(pdf.pages[1].mediabox.width), 210*72/25.4, places=2)
        self.assertAlmostEqual(float(pdf.pages[1].mediabox.height), 297*72/25.4, places=2)


@unittest.skipUnless(os.environ.get('SMARTCORRECTION_TEST_PDF') == '1', 'PDF integration runs in the dedicated LaTeX job')
class WorkflowV2PdfTests(WorkflowV2Tests):
    def test_corrige_preview_uses_selected_size_before_grid(self):
        self.app.save_formats(self.ident, 'A6', 'A5')
        self.app.exchange(self.ident, 'corriges', json.dumps(self.corriges(), ensure_ascii=False), True)
        pdf = PdfReader(io.BytesIO(self.app.corrige_preview(self.ident)))
        self.assertGreaterEqual(len(pdf.pages), 2)
        self.assertAlmostEqual(float(pdf.pages[0].mediabox.width), 148*72/25.4, places=2)
        self.assertAlmostEqual(float(pdf.pages[0].mediabox.height), 210*72/25.4, places=2)


if __name__ == '__main__':
    unittest.main()
