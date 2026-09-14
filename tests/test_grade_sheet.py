import os
import unittest

from moteur.notes import config_from_mapping
from moteur.render import alphabetical_student_key, render_grade_sheet


class GradeSheetTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config_from_mapping({
            'note_individuelle': {'max': 20},
            'note_groupe': {'max': 0, 'mode': 'aucun'},
            'note_finale': {'max': 20, 'arrondi': .5},
            'absences': {'mode': 'exclure'},
        })

    def test_alphabetical_order_ignores_case_and_accents_and_puts_anonymous_last(self):
        students = [
            {'nom': 'Zulu', 'prenom': 'Zoé', 'eleve_id': 3, 'copie_id': 3, 'statut': 'present', 'note_finale': 11, 'label': 'Zulu'},
            {'nom': None, 'prenom': None, 'eleve_id': None, 'copie_id': 99, 'statut': 'present', 'note_finale': 9, 'label': 'C099 - élève non identifié'},
            {'nom': 'Éclair', 'prenom': 'Alice', 'eleve_id': 1, 'copie_id': 1, 'statut': 'present', 'note_finale': 15, 'label': 'Éclair'},
            {'nom': 'eclair', 'prenom': 'Benoît', 'eleve_id': 2, 'copie_id': 2, 'statut': 'present', 'note_finale': 14, 'label': 'eclair'},
        ]
        ordered = sorted(students, key=alphabetical_student_key)
        self.assertEqual([(s['nom'], s['prenom']) for s in ordered],
                         [('Éclair', 'Alice'), ('eclair', 'Benoît'), ('Zulu', 'Zoé'), (None, None)])
        source = render_grade_sheet(students, {'titre': 'Test', 'classe': '1GSpé'}, self.cfg)
        self.assertLess(source.index('Éclair'), source.index('eclair'))
        self.assertLess(source.index('eclair'), source.index('Zulu'))
        self.assertLess(source.index('Zulu'), source.index('C099'))
        self.assertIn('Note /20', source)


@unittest.skipUnless(os.environ.get('SMARTCORRECTION_TEST_PDF') == '1', 'PDF integration runs in the dedicated LaTeX job')
class FinalGradeSheetPdfTests(unittest.TestCase):
    def test_final_generation_creates_alphabetical_grade_pdf(self):
        from pypdf import PdfReader
        import test_gui

        fixture = test_gui.GuiWorkflowTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.pilot()
        fixture.exchange('correction', fixture.corrections(['C006']))
        result = fixture.app.generate(fixture.ident, final=True, pdf=True)
        self.assertIn('notes.pdf', result['fichiers'])
        text = '\n'.join(page.extract_text() for page in PdfReader(fixture.app.file('rendu', result['id'], 'notes.pdf')).pages)
        for name in ('Alpha', 'Beta', 'Delta', 'Epsilon', 'Eta', 'Gamma', 'C006'):
            self.assertIn(name, text)
        positions = [text.index(name) for name in ('Alpha', 'Beta', 'Delta', 'Epsilon', 'Eta', 'Gamma', 'C006')]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('Relevé des notes', text)


if __name__ == '__main__':
    unittest.main()
