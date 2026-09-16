import tempfile
import unittest
from pathlib import Path

from moteur import render
from moteur.gui_service import INDIVIDUAL
from moteur.notes import config_from_mapping
from moteur.workflow_v2 import WorkflowApplication


class Pr27CorrectionLayoutTests(unittest.TestCase):
    def student(self):
        return {
            'numero': 1, 'version': 'A', 'note_finale': 8.5, 'statut': 'present',
            'label': 'Alice DUPONT', 'nom': 'DUPONT', 'prenom': 'Alice',
            'camarades': [], 'etat_groupe': None,
            'commentaire_global': 'Travail sérieux.',
            'items': [
                {'code': 'E1Q1I1', 'exercice': '1', 'question': '1', 'description': 'Méthode', 'bareme_max': 1, 'points_obtenus': 1, 'commentaire': None, 'annotation': None},
                {'code': 'E1Q1I2', 'exercice': '1', 'question': '1', 'description': 'Calcul', 'bareme_max': 1, 'points_obtenus': .5, 'commentaire': 'Signe à revoir', 'annotation': None},
                {'code': 'E1Q2I1', 'exercice': '1', 'question': '2', 'description': 'Conclusion', 'bareme_max': 1, 'points_obtenus': 1, 'commentaire': None, 'annotation': None},
                {'code': 'E2Q1I1', 'exercice': '2', 'question': '1', 'description': 'Développement', 'bareme_max': 2, 'points_obtenus': 2, 'commentaire': None, 'annotation': None},
            ],
            'annotations': [],
            'conseils': [{'texte': 'Soigner les signes.'}],
            'corrige_latex': r'\\section*{Exercice 1} Corrigé.',
        }

    def test_student_sheet_has_compact_header_and_hierarchical_grid(self):
        tex = render.render_student(self.student(), {'titre': 'Interro 1', 'classe': 'TEST'}, config_from_mapping(INDIVIDUAL))
        self.assertIn(r'\\textbf{Interro 1}', tex)
        self.assertIn(r'\\textbf{Alice DUPONT}', tex)
        self.assertIn(r'\\textbf{Note :}', tex)
        self.assertIn(r'\\section*{Grille}', tex)
        self.assertIn(r'\\dotfill', tex)
        self.assertIn(r'\\noalign{\\hrule height 1.2pt}', tex)
        self.assertNotIn('À vérifier par le prof', tex)
        self.assertNotIn(r'\\SCtitle{Corrigé}', tex)

    def test_teacher_check_section_only_when_needed(self):
        student = self.student(); student['a_verifier'] = ['Version à confirmer']
        tex = render.render_student(student, {'titre': 'Interro 1', 'classe': 'TEST'}, config_from_mapping(INDIVIDUAL))
        self.assertIn('À vérifier par le prof', tex)
        self.assertIn('Version à confirmer', tex)

    def test_page_break_option_is_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = WorkflowApplication(root/'db.sqlite', root/'data', root/'legacy')
            app.roster('TEST', 'nom;prenom\nDUPONT;Alice\n', True)
            ident = app.create('TEST', 'Interro 1')['id']
            layout = app.state(ident)['layout']
            self.assertTrue(layout['correction']['newpage_after_correction'])
            layout['correction']['newpage_after_correction'] = False
            app.save_layout(ident, layout)
            self.assertFalse(app.state(ident)['layout']['correction']['newpage_after_correction'])


if __name__ == '__main__':
    unittest.main()
