import tempfile
import unittest
from pathlib import Path

from moteur.gui_prompts_v2 import make_prompt
from moteur.workflow_v2 import WorkflowApplication


class Pr18LayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.app = WorkflowApplication(root/'db.sqlite', root/'data', root/'legacy')
        self.app.roster('TEST', 'nom;prenom\nAlpha;Alice\n', True)
        self.ident = self.app.create('TEST', 'Sujet compact')['id']

    def test_default_layout_and_physical_summary(self):
        state = self.app.state(self.ident)
        self.assertEqual(state['layout']['correction']['size'], 'A6')
        self.assertEqual(state['layout']['corrige']['orientation'], 'portrait')
        self.assertEqual(state['layout']['assembly'], 'cote-a-cote')
        self.assertIn('A5 paysage', state['layout_summary'])

    def test_full_layout_is_saved_and_propagated_to_prompt(self):
        layout = {
            'correction': {'size': 'A6', 'orientation': 'portrait', 'pages': 1},
            'corrige': {'size': 'A5', 'orientation': 'paysage', 'pages': 2, 'columns': 2},
            'assembly': 'separe', 'print_format': 'A4',
        }
        self.app.save_layout(self.ident, layout)
        state = self.app.state(self.ident)
        self.assertEqual(state['layout'], layout)
        self.assertIn('impression terminale : A4', state['layout_summary'])
        prompt = make_prompt(self.app, self.ident, 'ouverture')
        self.assertIn('2 page(s) A5 paysage', prompt)
        self.assertIn('2 colonne(s)', prompt)
        self.assertIn('impression terminale A4', prompt)

    def test_invalid_layout_is_rejected(self):
        layout = {
            'correction': {'size': 'A3', 'orientation': 'portrait', 'pages': 1},
            'corrige': {'size': 'A6', 'orientation': 'portrait', 'pages': 1, 'columns': 1},
            'assembly': 'cote-a-cote', 'print_format': 'auto',
        }
        with self.assertRaises(ValueError):
            self.app.save_layout(self.ident, layout)


if __name__ == '__main__':
    unittest.main()
