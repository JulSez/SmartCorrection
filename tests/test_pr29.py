import tempfile
import unittest
from pathlib import Path

from moteur import render
from moteur.gui_prompts import make_prompt
from moteur.gui_service import INDIVIDUAL
from moteur.notes import config_from_mapping
from moteur.workflow_v2 import WorkflowApplication


class ReintegratedCorrectionLayoutTests(unittest.TestCase):
    def student(self):
        return {
            'numero': 1, 'version': 'A', 'note_finale': 8.5, 'statut': 'present',
            'label': 'Alice DUPONT', 'nom': 'DUPONT', 'prenom': 'Alice',
            'note_individuelle': 8.5, 'note_groupe': 0, 'camarades': [],
            'commentaire_global': 'Travail sérieux.',
            'items': [
                {'code': 'E1Q1I1', 'exercice': '1', 'question': '1', 'description': 'Méthode', 'bareme_max': 1, 'points_obtenus': 1, 'commentaire': None, 'annotation': None},
                {'code': 'E1Q1I2', 'exercice': '1', 'question': '1', 'description': 'Calcul', 'bareme_max': 1, 'points_obtenus': .5, 'commentaire': 'Signe à revoir', 'annotation': None},
                {'code': 'E1Q2I1', 'exercice': '1', 'question': '2', 'description': 'Conclusion', 'bareme_max': 1, 'points_obtenus': 1, 'commentaire': None, 'annotation': None},
                {'code': 'E2Q1I1', 'exercice': '2', 'question': '1', 'description': 'Développement', 'bareme_max': 2, 'points_obtenus': 2, 'commentaire': None, 'annotation': None},
            ],
            'annotations': [], 'conseils': [{'texte': 'Soigner les signes.'}],
            'a_verifier': [], 'corrige_latex': r'\section*{Exercice 1} Corrigé.',
        }

    def test_compact_header_hierarchical_grid_and_empty_checks(self):
        tex = render.render_student(self.student(), {'titre': 'Interro 1', 'classe': 'TEST'}, config_from_mapping(INDIVIDUAL))
        self.assertIn(r'\textbf{Interro 1}', tex)
        self.assertIn(r'\textbf{Alice DUPONT}', tex)
        self.assertIn(r'\textbf{Note :}', tex)
        self.assertNotIn(r'\section*{Correction}', tex)
        self.assertIn(r'\section*{Conseil}', tex)
        self.assertIn(r'\section*{Bilan par question}', tex)
        self.assertIn('Erreurs', tex)
        self.assertIn('Signe à revoir', tex)
        self.assertNotIn(r'\dotfill', tex)
        self.assertIn('1,5/2', tex)
        self.assertIn(r'\noalign{\hrule height 1.2pt}', tex)
        self.assertNotIn('À vérifier par le prof', tex)
        self.assertNotIn(r'\SCtitle{Corrigé}', tex)

    def test_teacher_checks_only_when_present(self):
        student = self.student()
        student['a_verifier'] = ['Lecture du signe à confirmer']
        tex = render.render_student(student, {'titre': 'Interro 1', 'classe': 'TEST'}, config_from_mapping(INDIVIDUAL))
        self.assertIn('Note provisoire', tex)
        self.assertIn('PROVISOIRE', tex)
        self.assertIn('À vérifier par le prof', tex)
        self.assertIn('Lecture du signe à confirmer', tex)

    def test_combining_math_accents_are_real_latex(self):
        tex = render.latex_escape_plain_text('Poser z̄ et v⃗')
        self.assertIn(r'\overline{z}', tex)
        self.assertIn(r'\vec{v}', tex)
        self.assertNotIn('U+0304', tex)
        self.assertNotIn('U+20D7', tex)

    def test_layout_option_defaults_true_and_can_be_disabled(self):
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

    def test_correction_prompt_exposes_non_blocking_verification_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = WorkflowApplication(root/'db.sqlite', root/'data', root/'legacy')
            app.roster('TEST', 'nom;prenom\nDUPONT;Alice\n', True)
            ident = app.create('TEST', 'Interro 1')['id']
            source = Path(__file__).resolve().parents[1] / 'moteur' / 'gui_prompts.py'
            text = source.read_text(encoding='utf-8')
            self.assertIn("'a_verifier':[]", text)
            self.assertIn('incertitudes non bloquantes', text)


if __name__ == '__main__':
    unittest.main()
