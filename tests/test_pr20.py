import json
import tempfile
import unittest
from pathlib import Path

from moteur.gui_prompts_v2 import make_prompt
from moteur.workflow_v2 import WorkflowApplication


class Pr20HotfixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.app = WorkflowApplication(root/'db.sqlite', root/'data', root/'legacy')
        self.app.roster('TEST', 'nom;prenom\nAlpha;Alice\n', True)
        self.ident = self.app.create('TEST', 'Sujet')['id']

    def test_navigation_has_six_steps_and_no_uploaded_subject_gate(self):
        root = Path(__file__).resolve().parents[1]
        source = (root/'moteur'/'web'/'hotfix-pr20.js').read_text(encoding='utf-8')
        self.assertNotIn("role==='sujet'", source)
        self.assertNotIn('Ajoutez le sujet avant de demander les corrigés', source)
        self.assertIn("'Préparation','Corrigés','Grille','Tester la correction','Corriger le lot','Résultats et retour'", source)
        self.assertIn('Étape 1/6', source)
        self.assertNotIn('Importer le prétraitement', source)

    def test_step_one_has_four_clear_sections(self):
        root = Path(__file__).resolve().parents[1]
        source = (root/'moteur'/'web'/'hotfix-pr20.js').read_text(encoding='utf-8')
        layout = (root/'moteur'/'web'/'layout-v3.js').read_text(encoding='utf-8')
        self.assertIn('1. Format de mise en page', layout)
        self.assertIn('2. Préparation des documents', source)
        self.assertIn('3. Initialisation de l’IA', source)
        self.assertIn('4. Résultats de l’initialisation', source)
        self.assertIn('Première lecture des copies', source)
        self.assertIn('Consigne à copier dans l’IA', source)
        self.assertIn('Résultat de l’initialisation au format JSON', source)

    def test_hotfix_loads_after_layout_layer_and_is_served(self):
        root = Path(__file__).resolve().parents[1]
        index = (root/'moteur'/'web'/'index.html').read_text(encoding='utf-8')
        gui = (root/'moteur'/'gui.py').read_text(encoding='utf-8')
        self.assertLess(index.index('/layout-v3.js'), index.index('/hotfix-pr20.js'))
        self.assertIn("'/hotfix-pr20.js'", gui)

    def test_opening_prompt_starts_first_reading_and_common_error_analysis(self):
        prompt = make_prompt(self.app, self.ident, 'ouverture')
        self.assertIn('première lecture transversale', prompt)
        self.assertIn('repère les limites de chaque copie, leurs pages et leur version probable', prompt)
        self.assertIn('erreurs communes', prompt)
        self.assertIn('servira ensuite au corrigé de référence et à la grille', prompt)

    def test_preprocessing_is_saved_in_step_one_without_pdf_upload(self):
        payload = {
            'dossier': self.ident,
            'revision': 0,
            'copies': [
                {'reference': 'C001', 'numero': None, 'version': 'A', 'pages': [1, 2]},
                {'reference': 'C002', 'numero': None, 'version': 'B', 'pages': [3]},
            ],
            'pages_ignorees': [{'page': 4, 'motif': 'page blanche'}],
            'absents': [],
        }
        result = self.app.exchange(self.ident, 'pretraitement', json.dumps(payload), True)
        self.assertEqual(result['copies'], 2)
        state = self.app.state(self.ident)
        self.assertEqual(len(state['pretraitement']['copies']), 2)
        self.assertEqual(state['fichiers'], [])

    def test_non_anonymous_mode_asks_for_names_and_resolves_roster(self):
        result = self.app.save_anonymity(self.ident, False)
        self.assertFalse(result['anonymat'])
        state = self.app.state(self.ident)
        self.assertFalse(state['anonymat'])
        prompt = make_prompt(self.app, self.ident, 'pretraitement')
        self.assertIn('MODE NON ANONYME ACTIF', prompt)
        self.assertIn('"nom": "DUPONT"', prompt)
        self.assertIn('"prenom": "Alice"', prompt)
        payload = {
            'dossier': self.ident,
            'revision': 0,
            'copies': [{'reference': 'C001', 'numero': None, 'nom': 'Alpha', 'prenom': 'Alice',
                        'version': 'A', 'pages': [1]}],
            'pages_ignorees': [],
            'absents': [],
        }
        result = self.app.exchange(self.ident, 'pretraitement', json.dumps(payload), True)
        self.assertEqual(result['identifiees'], 1)
        saved = self.app.state(self.ident)['pretraitement']['copies'][0]
        self.assertEqual(saved['nom'], 'Alpha')
        self.assertEqual(saved['prenom'], 'Alice')
        self.assertIsInstance(saved['eleve_id'], int)

    def test_anonymity_mode_change_invalidates_saved_preprocessing(self):
        payload = {
            'dossier': self.ident, 'revision': 0,
            'copies': [{'reference': 'C001', 'numero': None, 'version': 'A', 'pages': [1]}],
            'pages_ignorees': [], 'absents': [],
        }
        self.app.exchange(self.ident, 'pretraitement', json.dumps(payload), True)
        self.assertIsNotNone(self.app.state(self.ident)['pretraitement'])
        result = self.app.save_anonymity(self.ident, False)
        self.assertTrue(result['pretraitement_invalide'])
        self.assertIsNone(self.app.state(self.ident)['pretraitement'])

    def test_ui_exposes_anonymity_selector(self):
        root = Path(__file__).resolve().parents[1]
        source = (root/'moteur'/'web'/'hotfix-pr20.js').read_text(encoding='utf-8')
        self.assertIn('Anonymat activé (défaut)', source)
        self.assertIn('Anonymat désactivé — l’IA renvoie les noms', source)
        gui = (root/'moteur'/'gui.py').read_text(encoding='utf-8')
        self.assertIn("action=='anonymat'", gui)

    def test_corrige_and_grid_prompts_reuse_first_reading(self):
        corrige = make_prompt(self.app, self.ident, 'corriges')
        self.assertIn('première lecture transversale des copies', corrige)
        self.assertIn('erreurs communes', corrige)


if __name__ == '__main__':
    unittest.main()
