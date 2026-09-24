import json
import tempfile
import unittest
from pathlib import Path
from moteur.workflow_v2 import WorkflowApplication
from moteur.gui import dispatch
from moteur.gui_prompts_v2 import make_prompt
from moteur.instructions import policies, replace_policy, set_type
from moteur.db import database


class InstructionEditorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.app = WorkflowApplication(root/'db',root/'data',root/'legacy')
        for classe,nom in (('TMEX','Secret;Alice'),('SPE','Martin;Bernard')):
            self.app.roster(classe,'nom;prenom\n'+nom+'\n',True)
        self.ident = dispatch(self.app,{'action':'creer','classe':'TMEX','titre':'Test','type_epreuve':' DST '})['id']

    def test_scopes_persist_and_do_not_leak_between_class_or_type(self):
        replace_policy(self.app,'generales','','','Règle générale.',None)
        replace_policy(self.app,'classe','TMEX','','Aligner les égalités.',None)
        replace_policy(self.app,'type','TMEX','DST','Justifier chaque étape.',None)
        state = self.app.state(self.ident)
        self.assertEqual(state['dossier']['type_epreuve'],'dst')
        prompt = make_prompt(self.app,self.ident,'bareme')
        for text in ('Règle générale.','Aligner les égalités.','Justifier chaque étape.'):
            self.assertEqual(prompt.count(text),1)
        self.assertNotIn('Alice',prompt)
        self.assertEqual(policies(self.app,'TMEX','interro')['type']['texte'],'')
        self.assertEqual(policies(self.app,'SPE','DST')['type']['texte'],'')
        reopened = WorkflowApplication(self.app.db_path,self.app.data_dir)
        self.assertEqual(reopened.state(self.ident)['consignes']['type']['texte'],'Justifier chaque étape.')
        set_type(self.app,self.ident,'DM')
        self.assertNotIn('Justifier chaque étape.',make_prompt(self.app,self.ident,'bareme'))
        self.assertEqual(policies(self.app,'TMEX','DST')['type']['texte'],'Justifier chaque étape.')

    def test_explicit_replacement_conflicts_and_history(self):
        first = replace_policy(self.app,'type','TMEX','DM','Ancien',None)['revision']
        second = replace_policy(self.app,'type','TMEX','dm','Nouveau',first)['revision']
        with self.assertRaisesRegex(ValueError,'changé'):
            replace_policy(self.app,'type','TMEX','DM','Obsolète',first)
        self.assertEqual([r['id'] for r in policies(self.app,'TMEX','DM')['historique_type']],[second,first])
        with self.assertRaises(ValueError):
            replace_policy(self.app,'type','TMEX','','Texte',None)
        with self.assertRaises(ValueError):
            replace_policy(self.app,'classe','Inconnue','','Texte',None)

    def test_typed_feedback_is_atomic_and_uses_current_policy(self):
        with database(self.app.db_path) as conn:
            conn.execute('UPDATE ui_dossier SET termine=1 WHERE id=?',(self.ident,))
        prompt = make_prompt(self.app,self.ident,'retour')
        value = json.loads(prompt.split('```json\n')[1].split('\n```')[0])
        value.update(generales='Bref',classe='Classe',type='DST uniquement')
        replace_policy(self.app,'type','TMEX','DST','Modification concurrente',None)
        with self.assertRaisesRegex(ValueError,'changé'):
            self.app.exchange(self.ident,'retour',json.dumps(value),True)
        self.assertIsNone(policies(self.app,'TMEX','DST')['generales']['id'])
        value['base_type'] = policies(self.app,'TMEX','DST')['type']['id']
        preview = self.app.exchange(self.ident,'retour',json.dumps(value),False)
        self.assertEqual(preview['type']['apres'],'DST uniquement')
        self.assertEqual(policies(self.app,'TMEX','DST')['type']['texte'],'Modification concurrente')
        self.app.exchange(self.ident,'retour',json.dumps(value),True)
        self.assertEqual(policies(self.app,'TMEX','DST')['type']['texte'],'DST uniquement')
        self.app.delete(self.ident,True)
        self.assertEqual(policies(self.app,'TMEX','DST')['type']['texte'],'DST uniquement')
        with database(self.app.db_path) as conn:
            self.assertFalse(list(conn.execute('PRAGMA foreign_key_check')))

    def test_feedback_from_another_type_is_rejected_even_without_saved_policies(self):
        with database(self.app.db_path) as conn:
            conn.execute('UPDATE ui_dossier SET termine=1 WHERE id=?',(self.ident,))
        prompt = make_prompt(self.app,self.ident,'retour')
        value = json.loads(prompt.split('```json\n')[1].split('\n```')[0])
        set_type(self.app,self.ident,'DM')
        with self.assertRaisesRegex(ValueError,'type d’épreuve a changé'):
            self.app.exchange(self.ident,'retour',json.dumps(value),True)
        self.assertIsNone(policies(self.app,'TMEX','DM')['generales']['id'])
