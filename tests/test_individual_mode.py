import unittest

from moteur.notes import config_from_mapping, compute_final_note, compute_group_score
from moteur.render import render_student


class IndividualModeTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config_from_mapping({
            'note_individuelle': {'max': 20, 'arrondi': None},
            'note_groupe': {'max': 0, 'mode': 'aucun', 'arrondi': None, 'sans_camarades': 'zero'},
            'note_finale': {
                'max': 20,
                'arrondi': 0.5,
                'arrondi_mode': 'demi_superieur',
                'poids_individuel': 1,
                'poids_groupe': 0,
                'bonus': 0,
            },
            'absences': {'mode': 'exclure'},
        })

    def test_individual_score_is_final_score(self):
        self.assertEqual(compute_group_score([], self.cfg), 0)
        self.assertEqual(compute_final_note(13.5, 0, self.cfg), 13.5)

    def test_render_hides_group_columns(self):
        student = {
            'numero': 7,
            'version': 'A',
            'statut': 'present',
            'note_individuelle': 13.5,
            'note_groupe': 0,
            'note_finale': 13.5,
            'camarades': [],
            'items': [],
            'annotations': [],
            'conseils': [],
            'commentaire_global': None,
            'corrige_latex': None,
        }
        tex = render_student(student, {'classe': '1GSpé', 'titre': 'Évaluation'}, self.cfg)
        self.assertIn(r'\\textbf{Note :} 13,5/20', tex)
        self.assertNotIn('Note groupe', tex)
        self.assertNotIn('Aucun camarade', tex)


if __name__ == '__main__':
    unittest.main()
