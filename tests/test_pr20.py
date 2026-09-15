import tempfile
import unittest
from pathlib import Path

from moteur.gui_prompts_v2 import make_prompt
from moteur.workflow_v2 import WorkflowApplication


class Pr20HotfixTests(unittest.TestCase):
    def test_navigation_no_longer_requires_uploaded_subject(self):
        root = Path(__file__).resolve().parents[1]
        source = (root/'moteur'/'web'/'hotfix-pr20.js').read_text(encoding='utf-8')
        self.assertNotIn("role==='sujet'", source)
        self.assertNotIn('Ajoutez le sujet avant de demander les corrigés', source)
        self.assertIn('!latest.corriges_valides', source)
        self.assertIn("stages[3]='Importer le prétraitement'", source)

    def test_hotfix_loads_after_layout_layer(self):
        root = Path(__file__).resolve().parents[1]
        index = (root/'moteur'/'web'/'index.html').read_text(encoding='utf-8')
        self.assertLess(index.index('/layout-v3.js'), index.index('/hotfix-pr20.js'))

    def test_opening_prompt_starts_copy_preprocessing_immediately(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        app = WorkflowApplication(root/'db.sqlite', root/'data', root/'legacy')
        app.roster('TEST', 'nom;prenom\nAlpha;Alice\n', True)
        ident = app.create('TEST', 'Sujet')['id']
        prompt = make_prompt(app, ident, 'ouverture')
        self.assertIn('commence aussi le prétraitement du paquet', prompt)
        self.assertIn('repère les limites de chaque copie, leurs pages et leur version probable', prompt)


if __name__ == '__main__':
    unittest.main()
