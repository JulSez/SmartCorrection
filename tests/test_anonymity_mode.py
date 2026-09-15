import json
import tempfile
import unittest
from pathlib import Path

from moteur.gui_prompts_v2 import make_prompt
from moteur.workflow_v2 import WorkflowApplication


class OptionalAnonymityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.app = WorkflowApplication(root/'db.sqlite', root/'data', root/'legacy')
        self.app.roster('TEST', 'nom;prenom\nDupont;Alice\nMartin;Bob\n', True)
        self.ident = self.app.create('TEST', 'Sujet')['id']

    def payload(self, **copy):
        base = {'reference':'C001','numero':None,'version':'A','pages':[1]}
        base.update(copy)
        return {'dossier':self.ident,'revision':0,'copies':[base],'pages_ignorees':[],'absents':[]}

    def test_anonymity_is_default(self):
        state = self.app.state(self.ident)
        self.assertTrue(state['anonymat'])
        prompt = make_prompt(self.app, self.ident, 'pretraitement')
        self.assertIn('MODE ANONYMAT : actif', prompt)
        self.assertNotIn('"nom": "DUPONT"', prompt)

    def test_non_anonymous_mode_accepts_names_and_updates_prompt(self):
        self.app.save_anonymity(self.ident, False)
        prompt = make_prompt(self.app, self.ident, 'pretraitement')
        self.assertIn('MODE ANONYMAT : désactivé', prompt)
        self.assertIn('"nom": "DUPONT"', prompt)
        result = self.app.exchange(self.ident, 'pretraitement', json.dumps(self.payload(nom='Dupont', prenom='Alice')), True)
        self.assertEqual(result['copies'], 1)
        state = self.app.state(self.ident)
        self.assertFalse(state['anonymat'])
        self.assertEqual(state['pretraitement']['copies'][0]['nom'], 'Dupont')
        self.assertEqual(state['pretraitement']['copies'][0]['prenom'], 'Alice')

    def test_mode_is_locked_after_initialization_result(self):
        self.app.save_anonymity(self.ident, False)
        self.app.exchange(self.ident, 'pretraitement', json.dumps(self.payload(nom='Dupont', prenom='Alice')), True)
        with self.assertRaisesRegex(ValueError, 'ne peut plus être modifié'):
            self.app.save_anonymity(self.ident, True)

    def test_ui_exposes_clear_mode_choice(self):
        source = (Path(__file__).resolve().parents[1]/'moteur'/'web'/'hotfix-pr20.js').read_text(encoding='utf-8')
        self.assertIn('Mode anonymat — références C001, C002…', source)
        self.assertIn('Anonymat désactivé — noms/prénoms visibles par l’IA', source)
        self.assertIn("action:'anonymat'", source)


if __name__ == '__main__':
    unittest.main()
