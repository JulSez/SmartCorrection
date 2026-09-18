import json
import tempfile
import unittest
from pathlib import Path

from moteur.workflow_v2 import WorkflowApplication


class FlexibleCopyIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.app = WorkflowApplication(root/'db.sqlite', root/'data', root/'legacy')
        self.app.roster('TEST', 'nom;prenom\nAlpha;Alice\nBeta;Bob\n', True)
        self.ident = self.app.create('TEST', 'Sujet')['id']

    def _payload(self):
        return {
            'dossier': self.ident,
            'revision': 0,
            'copies': [
                {'reference': 'C001', 'numero': None, 'version': 'A', 'pages': [1]},
                {'reference': 'C002', 'numero': None, 'version': 'A', 'pages': [2]},
            ],
            'pages_ignorees': [],
            'absents': [],
        }

    def test_non_anonymous_mode_accepts_copies_without_identity(self):
        self.app.save_anonymity(self.ident, False)
        result = self.app.exchange(self.ident, 'pretraitement', json.dumps(self._payload()), True)
        self.assertEqual(result['copies'], 2)
        state = self.app.state(self.ident)
        self.assertIsNone(state['pretraitement']['copies'][0].get('nom'))
        self.assertEqual(len(state['eleves']), 2)
        self.assertEqual([s['numero'] for s in state['eleves']], [1, 2])

    def test_teacher_can_assign_or_leave_copy_unassigned(self):
        self.app.save_anonymity(self.ident, False)
        self.app.exchange(self.ident, 'pretraitement', json.dumps(self._payload()), True)
        state = self.app.state(self.ident)
        student = state['eleves'][0]
        self.app.review(self.ident, f"@affectation:C001:{student['id']}")
        state = self.app.state(self.ident)
        copy = next(c for c in state['pretraitement']['copies'] if c['reference'] == 'C001')
        self.assertEqual(copy['eleve_id'], student['id'])
        self.assertEqual(copy['nom'], student['nom'])
        self.app.review(self.ident, '@affectation:C001:')
        state = self.app.state(self.ident)
        copy = next(c for c in state['pretraitement']['copies'] if c['reference'] == 'C001')
        self.assertIsNone(copy.get('eleve_id'))
        self.assertTrue(copy.get('affectation_bloquee'))
        # Reloading state must not auto-match the old name back onto the copy.
        state = self.app.state(self.ident)
        copy = next(c for c in state['pretraitement']['copies'] if c['reference'] == 'C001')
        self.assertIsNone(copy.get('eleve_id'))

    def test_clear_blocks_name_based_rematch_in_non_anonymous_mode(self):
        self.app.save_anonymity(self.ident, False)
        payload = self._payload()
        payload['copies'][0]['nom'] = 'Alpha'
        payload['copies'][0]['prenom'] = 'Alice'
        self.app.exchange(self.ident, 'pretraitement', json.dumps(payload), True)
        state = self.app.state(self.ident)
        copy = next(c for c in state['pretraitement']['copies'] if c['reference'] == 'C001')
        self.assertIsNotNone(copy.get('eleve_id'))
        self.app.review(self.ident, '@affectation:C001:')
        state = self.app.state(self.ident)
        copy = next(c for c in state['pretraitement']['copies'] if c['reference'] == 'C001')
        self.assertIsNone(copy.get('eleve_id'))
        self.assertEqual(copy.get('nom'), 'Alpha')
        self.assertEqual(copy.get('prenom'), 'Alice')

    def test_identity_read_accepts_number_or_name_and_can_be_adjusted(self):
        payload = self._payload()
        payload['copies'][0]['identite_lue'] = 'n° 1'
        payload['copies'][1]['identite_lue'] = 'Bob Beta'
        self.app.exchange(self.ident, 'pretraitement', json.dumps(payload), True)
        state = self.app.state(self.ident)
        copies = {c['reference']: c for c in state['pretraitement']['copies']}
        students = {s['numero']: s for s in state['eleves']}
        self.assertEqual(copies['C001']['identite_lue'], 'n° 1')
        self.assertEqual(copies['C001']['eleve_id'], students[1]['id'])
        self.assertEqual(copies['C002']['eleve_id'], students[2]['id'])
        self.app.review(self.ident, '@affectation:C001:')
        state = self.app.state(self.ident)
        copy = next(c for c in state['pretraitement']['copies'] if c['reference'] == 'C001')
        self.assertIsNone(copy.get('eleve_id'))
        self.assertEqual(copy['identite_lue'], 'n° 1')

    def test_ui_exposes_manual_assignment_and_unassigned_choice(self):
        root = Path(__file__).resolve().parents[1]
        source = (root/'moteur'/'web'/'hotfix-pr20.js').read_text(encoding='utf-8')
        self.assertIn('Affectation locale des élèves', source)
        self.assertIn('Identité lue par l’IA', source)
        self.assertIn('c.identite_lue', source)
        self.assertIn('N° ou nom de l’élève', source)
        self.assertIn('normalizeStudentSearch', source)
        self.assertIn('part.startsWith(q)', source)
        self.assertIn('Une copie peut rester sans élève', source)
        self.assertIn('@affectation:', source)


if __name__ == '__main__':
    unittest.main()
