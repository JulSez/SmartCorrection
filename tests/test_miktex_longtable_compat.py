import inspect
import unittest

from moteur.notes import config_from_mapping
from moteur.render import render_student


class MiktexLongtableCompatibilityTests(unittest.TestCase):
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
        self.student = {
            'numero': 27,
            'version': 'A',
            'statut': 'present',
            'note_individuelle': 15.0,
            'note_groupe': 0,
            'note_finale': 15.0,
            'camarades': [],
            'items': [{
                'exercice': '1',
                'question': '1',
                'description': 'Critère',
                'points_obtenus': 2,
                'bareme_max': 2,
                'commentaire': 'Retour',
                'annotation': None,
            }],
            'annotations': [],
            'conseils': [],
            'commentaire_global': None,
            'corrige_latex': r'$x=2$.',
        }

    def test_render_avoids_colortbl_longtable_patch(self):
        tex = render_student(self.student, {'classe': '1GSpé', 'titre': 'Évaluation'}, self.cfg)
        self.assertIn(r'\usepackage{xcolor}', tex)
        self.assertIn(r'\begin{longtable}', tex)
        self.assertNotIn(r'\usepackage[table]{xcolor}', tex)
        self.assertNotIn(r'\rowcolor', tex)
        self.assertNotIn(r'\arrayrulecolor', tex)

        source = inspect.getsource(render_student)
        self.assertNotIn('insert@pcolumn', source)
        self.assertNotIn('rowcolor', source)
        self.assertNotIn('arrayrulecolor', source)


if __name__ == '__main__':
    unittest.main()
