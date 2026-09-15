import tempfile
import unittest
from pathlib import Path

from moteur.gui_prompts_v2 import make_prompt
from moteur.workflow_v2 import WorkflowApplication


class Pr19Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.app = WorkflowApplication(root/'db.sqlite', root/'data', root/'legacy')
        self.app.roster('TEST', 'nom;prenom\nAlpha;Alice\n', True)
        self.ident = self.app.create('TEST', 'Sujet')['id']

    def test_opening_prompt_lists_direct_ai_attachments_without_upload_state(self):
        prompt = make_prompt(self.app, self.ident, 'ouverture')
        self.assertIn('copies, sujet, éventuel corrigé et documents de cours de référence', prompt)
        self.assertIn('joint directement à cette conversation IA', prompt)

    def test_first_step_has_three_clear_sections_and_no_upload_control(self):
        root = Path(__file__).resolve().parents[1]
        source = (root/'moteur'/'web'/'layout-v3.js').read_text(encoding='utf-8')
        self.assertIn('Étape 1/7', source)
        self.assertIn('1. Format de mise en page', source)
        self.assertIn('2. Préparation des documents', source)
        self.assertIn('3. Initialisation de l’IA', source)
        self.assertNotIn('id="upload-file"', source)
        self.assertNotIn('id="pdf-file"', source)


if __name__ == '__main__':
    unittest.main()
