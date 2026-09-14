"""Final document exclusions are durable output choices, never deleted corrections."""
import csv
import io
import json
import unittest

import test_gui
from moteur.db import database
from moteur.gui import dispatch
from moteur.gui_prompts import make_prompt
from moteur.gui_service import Application


class FinalSelectionTests(unittest.TestCase):
    def setUp(self):
        self.f = test_gui.GuiWorkflowTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.app, self.ident = self.f.app, self.f.ident

    def include(self, ref, include):
        return dispatch(self.app, {'action': 'selection_finale', 'dossier': self.ident,
                                  'reference': ref, 'inclure': include})

    def result(self, final=True):
        r = self.app.generate(self.ident, final=final, pdf=False)
        data = json.loads(self.app.file('rendu', r['id'], 'notes.json').read_text())
        return r, data

    def test_reversible_persistent_selection_preserves_scores_and_sample(self):
        first = self.f.finish()
        sample, _ = self.result(final=False)
        before = self.app.state(self.ident)['copies']
        self.assertTrue(all(not c['exclue_final'] for c in before))
        self.include('C001', False)
        self.app = Application(self.app.db_path, self.app.data_dir, self.f.root/'legacy')
        state = self.app.state(self.ident)
        self.assertFalse(state['dossier']['termine'])
        self.assertTrue(state['dossier']['echantillon_valide'])
        validity = {r['id']: r['valide'] for r in state['rendus']}
        self.assertFalse(validity[first['id']])
        self.assertTrue(validity[sample['id']])
        after = state['copies']
        for a, b in zip(before, after):
            self.assertEqual({k: v for k, v in a.items() if k != 'exclue_final'},
                             {k: v for k, v in b.items() if k != 'exclue_final'})
        rendered, data = self.result()
        self.assertEqual(data['copies_exclues'], ['C001'])
        self.assertEqual(len(data['notes']), 6)
        self.assertNotIn('eleve_001.tex', rendered['fichiers'])
        self.assertNotIn(1, [s['eleve_id'] for s in data['fiches']])
        rows = list(csv.DictReader(io.StringIO(self.app.file('rendu', rendered['id'], 'notes.csv').read_text(encoding='utf-8-sig')), delimiter=';'))
        self.assertEqual(len(rows), 6)
        self.assertNotIn('1', [r['eleve_id'] for r in rows])
        # Retrying the same state is idempotent and does not stale a valid final.
        self.include('C001', False)
        self.assertTrue(self.app.state(self.ident)['dossier']['termine'])
        _, sample_data = self.result(final=False)
        self.assertIn(1, [s['eleve_id'] for s in sample_data['notes']])
        self.include('C001', True)
        self.assertFalse(self.app.state(self.ident)['dossier']['termine'])
        _, restored = self.result()
        self.assertEqual(restored['copies_exclues'], [])
        self.assertEqual(len(restored['notes']), 7)
        self.assertEqual(next(r for r in restored['notes'] if r['eleve_id']==1)['note_finale'], 13.5)

    def test_ungraded_or_flagged_copy_can_be_excluded_and_returns_to_prompt(self):
        self.f.pilot()
        with self.assertRaisesRegex(ValueError, 'non corrigée'):
            self.result()
        self.include('C006', False)
        _, data = self.result()
        self.assertEqual(len(data['notes']), 6)
        with self.assertRaisesRegex(ValueError, 'Aucune copie'):
            make_prompt(self.app, self.ident, 'correction', mode='reste')
        self.include('C006', True)
        self.assertIn('C006', make_prompt(self.app, self.ident, 'correction', mode='reste'))
        self.f.exchange('correction', {'corrections': [], 'a_revoir': [{'reference': 'C006', 'motif': 'Illisible'}]})
        with self.assertRaisesRegex(ValueError, 'reste à revoir'):
            self.result()
        self.include('C006', False)
        self.result()
        self.assertEqual(next(c for c in self.app.state(self.ident)['copies'] if c['reference']=='C006')['a_revoir'], 'Illisible')

    def test_group_scores_keep_valid_excluded_peer_and_pending_unknown_peer(self):
        self.f.inventory['copies'][5]['numero'] = 6
        self.f.exchange('copies', self.f.inventory)
        self.app.groups(self.ident, True, '1,6\n2,3,4,5,7')
        self.f.pilot()
        self.include('C006', False)
        _, pending = self.result()
        row = next(r for r in pending['notes'] if r['numero']==1)
        self.assertIsNone(row['note_groupe'])
        self.assertIn('En attente', row['etat_groupe'])
        self.f.exchange('correction', self.f.corrections(['C006']))
        _, scored = self.result()
        row = next(r for r in scored['notes'] if r['numero']==1)
        self.assertAlmostEqual(row['note_groupe'], 10/3)
        self.assertEqual(row['camarades'][0]['statut'], 'present')
        self.assertNotIn(6, [r['numero'] for r in scored['notes']])

    def test_input_scope_empty_selection_and_revision_preservation(self):
        self.f.finish()
        for invalid in (None, 0, 1, 'false', []):
            with self.assertRaisesRegex(ValueError, 'booléen'):
                self.include('C001', invalid)
        with self.assertRaisesRegex(ValueError, 'introuvable'):
            self.include('C999', False)
        other = self.app.create('TEST', 'Autre dossier')['id']
        with self.assertRaisesRegex(ValueError, 'introuvable'):
            self.app.include_in_final(other, 'C001', False)
        self.assertTrue(self.app.state(self.ident)['dossier']['termine'])
        for c in self.app.state(self.ident)['copies']:
            self.include(c['reference'], False)
        count = len(self.app.state(self.ident)['rendus'])
        with self.assertRaisesRegex(ValueError, 'au moins une copie'):
            self.result()
        self.assertEqual(len(self.app.state(self.ident)['rendus']), count)
        self.f.exchange('grille', self.f.grid)
        self.assertTrue(all(c['exclue_final'] for c in self.app.state(self.ident)['copies']))

    def test_existing_database_starts_with_every_copy_included(self):
        self.f.finish()
        with database(self.app.db_path) as conn:
            conn.execute('DROP TABLE ui_copie_exclue')
        reopened = Application(self.app.db_path, self.app.data_dir, self.f.root/'legacy')
        self.assertTrue(all(not c['exclue_final'] for c in reopened.state(self.ident)['copies']))
        self.assertTrue(reopened.state(self.ident)['dossier']['termine'])


if __name__ == '__main__':
    unittest.main()
