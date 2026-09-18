import json
import tempfile
import unittest
from pathlib import Path

from moteur.gui_prompts_v2 import make_prompt
from moteur.workflow_v2 import WorkflowApplication


class FastCalibrationWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.app = WorkflowApplication(root/'db.sqlite', root/'data', root/'legacy')
        self.app.roster('TEST', 'nom;prenom\nAlpha;Alice\nBeta;Bob\nGamma;Chloe\nDelta;David\nEpsilon;Emma\nZeta;Zoe\n', True)
        self.ident = self.app.create('TEST', 'Interro')['id']

    def envelope(self, payload):
        state = self.app.state(self.ident)
        return dict(payload, dossier=self.ident, revision=state['dossier']['revision'])

    def test_bareme_then_two_calibration_batches(self):
        bareme = self.envelope({
            'versions': [{'version': 'A'}],
            'grilles': [{'nom': 'Barème', 'version': 'A', 'exercices': [
                {'numero': '1', 'questions': [{'numero': '1', 'items': [
                    {'code': 'E1Q1I1', 'description': 'Résoudre', 'bareme_max': 2},
                    {'code': 'E1Q1I2', 'description': 'Conclure', 'bareme_max': 1},
                ]}]}
            ]}],
        })
        self.app.exchange(self.ident, 'bareme', json.dumps(bareme), True)
        state = self.app.state(self.ident)
        self.assertEqual(state['dossier']['revision'], 1)
        self.assertEqual(len(state['grille']), 2)

        def correction(ref):
            return {'reference': ref, 'items': [
                {'item_code': 'E1Q1I1', 'points_obtenus': 1, 'commentaire': 'Erreur de calcul.'},
                {'item_code': 'E1Q1I2', 'points_obtenus': 1},
            ], 'annotations': [], 'conseils': [], 'commentaire_global': None, 'a_verifier': []}

        first = self.envelope({
            'pretraitement': {
                # numero stays local; identite_lue is what the AI actually sees on the copy.
                'copies': [{'reference': f'C{i:03d}', 'identite_lue': (str(i) if i <= 6 else None), 'version': 'A', 'pages': [i]} for i in range(1, 7)],
                'pages_ignorees': [], 'absents': [],
            },
            'corriges': [{'version': 'A', 'corrige_latex': r'\section*{Exercice 1} $x=2$.'}],
            'corrections': [correction(f'C{i:03d}') for i in range(1, 6)],
            'a_revoir': [], 'moyenne_estimee': 14.5,
        })
        self.app.exchange(self.ident, 'calibrage', json.dumps(first), True)
        state = self.app.state(self.ident)
        self.assertEqual(len(state['copies']), 6)
        self.assertEqual(sum(bool(c['correction_id']) for c in state['copies']), 5)
        self.assertEqual({c['reference'] for c in state['copies'] if c['echantillon']},
                         {f'C{i:03d}' for i in range(1, 6)})
        self.assertEqual(state['calibrage']['moyenne_estimee'], '14.5')

        self.app.draft(self.ident, 'calibrage-retours', 'Sanctionner davantage les petites erreurs de calcul.')
        self.app.sample(self.ident, ['C006'], False)
        prompt = make_prompt(self.app, self.ident, 'calibrage')
        self.assertIn('C006', prompt)
        self.assertIn('Sanctionner davantage', prompt)
        self.assertIn('moyenne estimée précédente est élevée', prompt)

        second = self.envelope({
            'corrections': [correction('C006')],
            'a_revoir': [], 'moyenne_estimee': 13.2,
        })
        self.app.exchange(self.ident, 'calibrage', json.dumps(second), True)
        state = self.app.state(self.ident)
        self.assertTrue(next(c for c in state['copies'] if c['reference']=='C006')['correction_id'])
        self.app.sample(self.ident, ['C006'], True)
        self.assertTrue(self.app.state(self.ident)['dossier']['echantillon_valide'])

    def test_calibration_accepts_code_alias_and_prompt_documents_item_code(self):
        bareme = self.envelope({
            'versions': [{'version': 'A'}],
            'grilles': [{'nom': 'Barème', 'version': 'A', 'exercices': [
                {'numero': '1', 'questions': [{'numero': '1', 'items': [
                    {'code': 'E1Q1I1', 'description': 'Résoudre', 'bareme_max': 2},
                ]}]}
            ]}],
        })
        self.app.exchange(self.ident, 'bareme', json.dumps(bareme), True)
        prompt = make_prompt(self.app, self.ident, 'calibrage')
        self.assertIn('"item_code": "E1Q1I1"', prompt)
        self.assertIn('jamais "code"', prompt)

        first = self.envelope({
            'pretraitement': {
                'copies': [{'reference': 'C001', 'identite_lue': '1', 'version': 'A', 'pages': [1]}],
                'pages_ignorees': [], 'absents': [],
            },
            'corriges': [{'version': 'A', 'corrige_latex': r'$x=2$.'}],
            'corrections': [{
                'reference': 'C001',
                'items': [{'code': 'E1Q1I1', 'points_obtenus': 1, 'commentaire': 'Erreur.'}],
                'annotations': [], 'conseils': [], 'commentaire_global': None, 'a_verifier': [],
            }],
            'a_revoir': [], 'moyenne_estimee': 10,
        })
        self.app.exchange(self.ident, 'calibrage', json.dumps(first), True)
        state = self.app.state(self.ident)
        self.assertTrue(state['copies'][0]['correction_id'])

    def test_prompts_match_fast_workflow(self):
        opening = make_prompt(self.app, self.ident, 'bareme')
        self.assertIn("Ne rends PAS le JSON", opening)
        self.assertIn("Quand l'enseignant valide le barème", opening)
        # After barème validation, the calibration prompt explicitly asks for the visible identity.
        bareme = self.envelope({'versions':[{'version':'A'}], 'grilles':[{'nom':'B','version':'A','exercices':[{'numero':'1','questions':[{'numero':'1','items':[{'code':'E1Q1I1','description':'Critère','bareme_max':1}]}]}]}]})
        self.app.exchange(self.ident, 'bareme', json.dumps(bareme), True)
        calibration = make_prompt(self.app, self.ident, 'calibrage')
        self.assertIn('identite_lue', calibration)
        self.assertIn('numéro écrit par l’élève', calibration)


if __name__ == '__main__':
    unittest.main()
