import io
import os
import unittest

from pypdf import PdfReader

from moteur.db import database
from moteur.grid_preview import blank_sheet_source, build_grid_preview
from moteur.notes import config_from_mapping
import test_gui


class GridPreviewSourceTests(unittest.TestCase):
    def test_blank_sheet_uses_final_layout_without_filled_scores(self):
        cfg = config_from_mapping({
            'note_individuelle': {'max': 20},
            'note_groupe': {'max': 0, 'mode': 'aucun'},
            'note_finale': {'max': 20, 'arrondi': .5},
            'absences': {'mode': 'exclure'},
        })
        source = blank_sheet_source(
            {'classe': 'TEST', 'titre': 'Évaluation'}, cfg, 'A',
            [{'exercice': '1', 'question': '1', 'description': 'Isoler x²', 'bareme_max': 2},
             {'exercice': '1', 'question': '2', 'description': 'Conclure', 'bareme_max': 1}],
        )
        self.assertTrue(source.startswith('% SmartCorrection: paired-a6-v1'))
        self.assertIn('paperwidth=105mm,paperheight=148mm', source)
        self.assertIn('Q. 1', source)
        self.assertNotIn('Isoler x', source)
        self.assertIn('/2', source)
        self.assertNotIn('0/2', source)
        self.assertNotIn('Aucun conseil enregistré.', source)
        self.assertIn('Le corrigé sera ajouté', source)


@unittest.skipUnless(os.environ.get('SMARTCORRECTION_TEST_PDF') == '1', 'PDF integration runs in the dedicated LaTeX job')
class GridPreviewPdfTests(unittest.TestCase):
    def test_preview_compiles_before_reference_correction_exists(self):
        fixture = test_gui.GuiWorkflowTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        # The preview belongs to the end of the grid step, before the reference correction.
        with database(fixture.app.db_path) as conn:
            conn.execute('DELETE FROM corrige')
        raw = build_grid_preview(fixture.app, fixture.ident)
        pdf = PdfReader(io.BytesIO(raw))
        self.assertGreaterEqual(len(pdf.pages), 1)
        first = pdf.pages[0]
        self.assertAlmostEqual(float(first.mediabox.width), 210*72/25.4, places=2)
        self.assertAlmostEqual(float(first.mediabox.height), 148*72/25.4, places=2)
        text = '\n'.join(page.extract_text() for page in pdf.pages)
        self.assertIn('Bilan par question', text)
        self.assertIn('Q. 1', text)
        self.assertIn('Le corrigé sera ajouté', text)


if __name__ == '__main__':
    unittest.main()
