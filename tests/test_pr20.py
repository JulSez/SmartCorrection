import unittest
from pathlib import Path


class Pr20HotfixTests(unittest.TestCase):
    def test_navigation_no_longer_requires_uploaded_subject(self):
        root = Path(__file__).resolve().parents[1]
        source = (root/'moteur'/'web'/'hotfix-pr20.js').read_text(encoding='utf-8')
        self.assertNotIn("role==='sujet'", source)
        self.assertNotIn('Ajoutez le sujet avant de demander les corrigés', source)
        self.assertIn('!latest.corriges_valides', source)

    def test_hotfix_loads_after_layout_layer(self):
        root = Path(__file__).resolve().parents[1]
        index = (root/'moteur'/'web'/'index.html').read_text(encoding='utf-8')
        self.assertLess(index.index('/layout-v3.js'), index.index('/hotfix-pr20.js'))


if __name__ == '__main__':
    unittest.main()
