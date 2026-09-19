"""Import the examples we actually give the AI and exercise the complete exchange."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from moteur.workflow_v2 import WorkflowApplication
from moteur.gui_prompts_v2 import make_prompt


class PromptWorkflowTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.app = WorkflowApplication(self.root/'db.sqlite', self.root/'data', self.root/'legacy')
        self.app.roster('TEST', 'nom;prenom\nSecret;Alice\nLocal;Bob\n', True)
        self.ident = self.app.create('TEST', 'Exemple')['id']

    def example(self, stage, **kwargs):
        prompt = make_prompt(self.app, self.ident, stage, **kwargs)
        return json.loads(prompt.split('```json\n')[1].split('\n```')[0])

    def submit(self, stage, value, commit=True):
        return self.app.exchange(self.ident, stage, json.dumps(value), commit)

    def start(self, two=False):
        self.submit('bareme', self.example('bareme'))
        value = self.example('calibrage')
        if two:
            value['pretraitement']['copies'].append(dict(value['pretraitement']['copies'][0], reference='C002', pages=[2]))
        self.submit('calibrage', value)
        return value

    def test_generated_examples_import_and_full_correction_uses_same_contract(self):
        self.start(two=True)
        self.app.sample(self.ident, ['C001'], True)
        value = self.example('correction', mode='reste')
        item = value['corrections'][0]['items'][0]
        # Compatibility is identical in the full correction and calibration routes.
        item['code'] = item.pop('item_code')
        value['corrections'][0]['conseils'] = [{'texte':'Vérifier le signe.', 'priorite':1}]
        self.submit('correction', value)
        output = self.app.generate(self.ident, final=True, pdf=False)
        data = json.loads(self.app.file('rendu', output['id'], 'notes.json').read_text())
        self.assertEqual(len(data['notes']), 2)
        self.submit('retour', dict(self.example('retour'), generales='Vérifier les signes.', classe='Aligner les égalités.'))
        self.assertTrue(self.app.instruction_history('TEST'))

    def test_prompts_are_short_single_contract_and_never_contain_local_roster(self):
        bareme = make_prompt(self.app, self.ident, 'bareme')
        self.assertLess(len(bareme), 2600)
        self.submit('bareme', self.example('bareme'))
        prompt = make_prompt(self.app, self.ident, 'calibrage')
        self.assertLess(len(prompt), 5700)
        self.assertEqual(prompt.count('FORMAT DES OBJETS'), 1)
        for word in ('Secret', 'Alice', 'Local', 'Bob', 'BLOC TECHNIQUE FIXE', 'moyenne estimée précédente est élevée'):
            self.assertNotIn(word, prompt)

    def test_anonymity_contract_and_validator_agree(self):
        self.submit('bareme', self.example('bareme'))
        value = self.example('calibrage')
        value['pretraitement']['copies'][0]['identite_lue'] = 'Alice Secret'
        with self.assertRaisesRegex(ValueError, 'Mode anonyme'):
            self.submit('calibrage', value)
        self.assertFalse(self.app.state(self.ident)['copies'])
        self.app.save_anonymity(self.ident, False)
        prompt = make_prompt(self.app, self.ident, 'calibrage')
        self.assertIn('Anonymat désactivé', prompt)
        self.assertNotIn('aucun nom/prénom', prompt)
        self.submit('calibrage', value)
        self.assertIsNotNone(self.app.state(self.ident)['copies'][0]['eleve_id'])

    def test_blocked_copy_is_part_of_calibration_not_an_invented_score(self):
        self.submit('bareme', self.example('bareme'))
        value = self.example('calibrage')
        value['corrections'] = []
        value['a_revoir'] = [{'reference':'C001','motif':'Page illisible'}]
        self.submit('calibrage', value)
        row = self.app.state(self.ident)['copies'][0]
        self.assertEqual(row['a_revoir'], 'Page illisible')
        self.assertIsNone(row['correction_id'])
        with self.assertRaises(ValueError):
            self.app.sample(self.ident, ['C001'], True)
        repaired = self.example('calibrage')
        self.assertNotIn('pretraitement', repaired)
        self.assertNotIn('corriges', repaired)
        self.submit('calibrage', repaired)
        self.app.sample(self.ident, ['C001'], True)

    def test_first_and_revised_grid_require_every_reference_transactionally(self):
        grid = self.example('bareme')
        grid['versions'].append({'version':'B'})
        grid['grilles'].append(dict(copy.deepcopy(grid['grilles'][0]), version='B', nom='B'))
        self.submit('bareme', grid)
        value = self.example('calibrage')
        self.assertEqual({v['version'] for v in value['corriges']}, {'A','B'})
        bad = copy.deepcopy(value); bad['corriges'].pop()
        with self.assertRaisesRegex(ValueError, 'Corrigé manquant'):
            self.submit('calibrage', bad)
        self.assertFalse(self.app.state(self.ident)['pretraitement'])
        self.assertFalse(self.app.state(self.ident)['copies'])
        self.submit('calibrage', value)
        grid['revision'] = self.app.state(self.ident)['dossier']['revision']
        self.submit('bareme', grid)
        next_value = self.example('calibrage')
        self.assertIn('corriges', next_value)
        self.assertNotIn('pretraitement', next_value)
        self.submit('calibrage', next_value)

    def test_policy_changes_flag_previous_copies_and_saved_drafts_survive(self):
        self.start(two=True)
        self.app.draft(self.ident, 'calibrage', '{"en cours":')
        self.app.draft(self.ident, 'bareme', 'Brouillon')
        reopened = WorkflowApplication(self.app.db_path, self.app.data_dir, self.root/'legacy')
        self.assertEqual(reopened.state(self.ident)['brouillons']['calibrage'], '{"en cours":')
        self.app.generate(self.ident, pdf=False)
        self.app.draft(self.ident, 'calibrage-retours', 'Ne pas pénaliser deux fois la même erreur.')
        state = self.app.state(self.ident)
        self.assertTrue(state['copies'][0]['a_revoir'])
        self.assertTrue(all(not r['valide'] for r in state['rendus']))
        self.assertFalse(self.app.draft(self.ident, 'calibrage-retours', 'Ne pas pénaliser deux fois la même erreur.')['enregistre'])
        self.app.sample(self.ident, ['C002'], False)
        self.submit('calibrage', self.example('calibrage'))
        self.app.sample(self.ident, ['C002'], True)
        remaining = self.example('correction', mode='reste')
        self.assertEqual(remaining['corrections'][0]['reference'], 'C001')
        self.submit('correction', remaining)
        self.app.generate(self.ident, final=True, pdf=False)

    @unittest.skipUnless(os.environ.get('SMARTCORRECTION_TEST_PDF')=='1', 'real PDF integration')
    def test_first_prompt_example_compiles_real_pdf(self):
        from pypdf import PdfReader
        self.start()
        self.app.sample(self.ident, ['C001'], True)
        result = self.app.generate(self.ident, final=True, pdf=True)
        reader = PdfReader(self.app.file('rendu', result['id'], 'corrections.pdf'))
        self.assertGreaterEqual(len(reader.pages), 1)


if __name__ == '__main__':
    unittest.main()
