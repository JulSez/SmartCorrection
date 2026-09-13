"""Real LaTeX compilation, enabled in the dedicated PDF CI job."""
import os
import unittest
from pypdf import PdfReader
import test_gui


@unittest.skipUnless(os.environ.get('SMARTCORRECTION_TEST_PDF') == '1', 'PDF integration runs in the dedicated LaTeX job')
class GuiPdfTests(unittest.TestCase):
    def test_fiches_and_combined_document(self):
        fixture = test_gui.GuiWorkflowTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.pilot()
        fixture.exchange('correction', fixture.corrections(['C006']))
        result = fixture.app.generate(fixture.ident, final=True, pdf=True)
        pdf = PdfReader(fixture.app.file('rendu', result['id'], 'corrections.pdf'))
        self.assertEqual(len(pdf.pages), 7)
        texts = [page.extract_text() for page in pdf.pages]
        self.assertIn('13,5', texts[1])
        self.assertTrue(any('C006' in text for text in texts))
        self.assertTrue(any('Absence' in text for text in texts))
        self.assertIn('Conseils', texts[1])
        self.assertIn('Corrigé', texts[1])
