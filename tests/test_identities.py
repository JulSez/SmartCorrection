import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import test_gui
from moteur.db import database, init_db, V3_SCHEMA, V4_SCHEMA
from moteur.gui_service import Application
from moteur.gui import dispatch
from moteur.identites import merge_pupils


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.app=Application(self.root/'db.sqlite',self.root/'data',self.root/'legacy')

    def seed(self, classe='A', text='nom;prenom\nDupont-Martin;Élodie Anne\n'):
        return self.app.roster(classe,text,True)['eleves'][0]['id']

    def save(self, classe, text, choices):
        preview=self.app.roster(classe,text)
        return self.app.roster(classe,text,True,choices,preview['empreinte'])

    def test_one_id_across_classes_variants_and_no_automatic_link(self):
        ident=self.seed()
        for classe,name in [('B','DUPONT;Elodie'),('C','dupont martin;elodie-anne'),('D','Dupond Martin;Elodie Anne')]:
            text='nom;prenom\n'+name+'\n'
            p=self.app.roster(classe,text)
            self.assertEqual(p['eleves'][0]['candidats'][0]['id'],ident)
            with self.assertRaisesRegex(ValueError,'rapprochement'):
                self.app.roster(classe,text,True)
            result=self.save(classe,text,[{'id':ident}])
            self.assertEqual(result['eleves'][0]['id'],ident)
        with database(self.app.db_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM eleve').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM eleve_classe').fetchone()[0],4)
            self.assertEqual(conn.execute('SELECT nom FROM eleve').fetchone()[0],'Dupont-Martin')

    def test_homonyms_and_duplicates_in_same_file_are_explicit(self):
        ident=self.seed()
        text='nom;prenom\nDupont-Martin;Élodie Anne\nDupont;Elodie\n'
        p=self.app.roster('B',text)
        self.assertEqual(p['eleves'][1]['lignes_proches'],[1])
        result=self.save('B',text,[{'nouveau':True},{'ligne':1}])
        self.assertEqual(result['effectif'],1)
        self.assertNotEqual(result['eleves'][0]['id'],ident)
        with database(self.app.db_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM eleve').fetchone()[0],2)

    def test_import_order_does_not_reassign_ids_and_stale_preview_rolls_back(self):
        self.seed(text='nom;prenom\nAlpha;Alice\nBeta;Bob\n')
        result=self.app.roster('A','nom;prenom\nBeta;Bob\nAlpha;Alice\n',True)
        self.assertEqual([e['id'] for e in result['eleves']],[1,2])
        text='nom;prenom\nGamma;Gina\n'
        preview=self.app.roster('B',text)
        self.seed('C','nom;prenom\nDelta;David\n')
        with self.assertRaisesRegex(ValueError,'changé'):
            self.app.roster('B',text,True,[{'nouveau':True}],preview['empreinte'])
        with database(self.app.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM eleve_classe WHERE classe='B'").fetchone()[0],0)

    def test_bad_decision_rolls_back_whole_import_and_id_cannot_change(self):
        self.seed()
        text='nom;prenom\nAucun;Arthur\nDupont;Elodie\n'
        with self.assertRaisesRegex(ValueError,'inconnu'):
            self.save('B',text,[{'nouveau':True},{'id':9999}])
        with database(self.app.db_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM eleve').fetchone()[0],1)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute('UPDATE eleve SET id=99')

    def test_dispatch_requires_decisions_and_returns_stable_ids(self):
        ident=self.seed()
        text='nom;prenom\nDupont;Elodie\n'
        p=dispatch(self.app,{'action':'classe','classe':'B','texte':text})
        result=dispatch(self.app,{'action':'classe','classe':'B','texte':text,'valider':True,
                                 'rapprochements':[{'id':ident}],'empreinte':p['empreinte']})
        self.assertEqual(result['eleves'][0]['id'],ident)

    def test_version_five_migration_keeps_ids_memberships_and_does_not_guess_homonyms(self):
        path=self.root/'v5.sqlite';conn=sqlite3.connect(path)
        legacy=Path('moteur/schema_legacy.sql').read_text()
        conn.executescript(legacy+V3_SCHEMA+V4_SCHEMA+legacy+'''
        INSERT INTO eleve(id,classe,numero,nom,prenom) VALUES(20,'A',1,'Dupont','Alice'),(34,'B',8,'Dupont','Alice');
        PRAGMA user_version=5;
        '''+Path('moteur/gui_schema.sql').read_text())
        conn.execute("INSERT INTO ui_dossier(id,classe,titre) VALUES('draft','A','Ancien dossier')")
        conn.execute("INSERT INTO ui_brouillon VALUES('draft','copies',?)",(json.dumps({'copies':[{'numero':1}],'absents':[]}),))
        conn.commit();conn.close()
        init_db(path);init_db(path)
        self.assertEqual(len(list(self.root.glob('v5.sqlite.avant-identites-*.sqlite'))),1)
        with database(path) as conn:
            self.assertEqual([tuple(r) for r in conn.execute('SELECT * FROM eleve_classe ORDER BY eleve_id')],[(20,'A',1),(34,'B',8)])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM eleve').fetchone()[0],2)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])
            draft=json.loads(conn.execute("SELECT texte FROM ui_brouillon WHERE dossier_id='draft'").fetchone()[0])
            self.assertEqual(draft['copies'][0]['numero'],20)
            ident=conn.execute("INSERT INTO eleve(nom,prenom) VALUES('Neuf','Zoe')").lastrowid
            self.assertGreater(ident,34)


class IdentityGradingTests(unittest.TestCase):
    def setUp(self):
        self.f=test_gui.GuiWorkflowTests();self.f.setUp();self.addCleanup(self.f.doCleanups)

    def test_same_id_in_another_class_uses_correct_groups_and_copies(self):
        f=self.f
        text='nom;prenom\nBeta;Benoit\nNouveau;Zoé\n'
        p=f.app.roster('OTHER',text)
        r=f.app.roster('OTHER',text,True,[{'id':2},{'nouveau':True}],p['empreinte'])
        self.assertEqual([x['id'] for x in r['eleves']],[2,8])
        old=f.ident
        f.ident=f.app.create('OTHER','Autre évaluation')['id']
        f.app.upload(f.ident,'paquet','paquet.pdf',__import__('base64').b64encode(f.app.file('source',f.source['id']).read_bytes()).decode())
        f.exchange('grille',f.grid);f.app.corrige(f.ident,'A','Corrigé.',True)
        f.exchange('copies',{'copies':[{'reference':'C001','numero':2,'version':'A','pages':[1]}, {'reference':'C002','numero':8,'version':'A','pages':[2]}],
                             'pages_ignorees':[{'page':n,'motif':'Hors évaluation'} for n in range(3,8)]})
        f.app.groups(f.ident,True,'2,8')
        f.exchange('correction',f.corrections(['C001','C002']))
        r=f.app.generate(f.ident,pdf=False)
        data=json.loads(f.app.file('rendu',r['id'],'notes.json').read_text())
        self.assertEqual([x['numero'] for x in data['notes']],[2,8])
        self.assertEqual(data['notes'][1]['camarades'][0]['numero'],2)
        self.assertIn('ID 8',data['fiches'][1]['label'])
        self.assertEqual(len(f.app.state(old)['eleves']),7)

    def test_explicit_merge_preserves_corrected_copies_scores_and_invalidates_pdf(self):
        f=self.f;f.pilot();render=f.app.generate(f.ident,pdf=False)
        text='nom;prenom\nAlpha;Alice\n'
        p=f.app.roster('OTHER',text)
        other=f.app.roster('OTHER',text,True,[{'nouveau':True}],p['empreinte'])['eleves'][0]['id']
        p=f.app.roster('TEST',text)
        self.assertEqual(p['eleves'][0]['inscrit_id'],1)
        with database(f.app.db_path) as conn:
            before=[tuple(r) for r in conn.execute('SELECT * FROM correction_item ORDER BY id')]
        f.app.roster('TEST',text,True,[{'id':other,'fusionner':1}],p['empreinte'])
        with database(f.app.db_path) as conn:
            self.assertIsNone(conn.execute('SELECT * FROM eleve WHERE id=1').fetchone())
            self.assertEqual(conn.execute('SELECT eleve_id FROM copie WHERE id=1').fetchone()[0],other)
            self.assertEqual(before,[tuple(r) for r in conn.execute('SELECT * FROM correction_item ORDER BY id')])
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(conn.execute('SELECT eleve_id FROM eleve_fusion WHERE ancien_id=1').fetchone()[0],other)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute('UPDATE copie SET eleve_id=2 WHERE id=1')
        self.assertFalse(next(x for x in f.app.state(f.ident)['rendus'] if x['id']==render['id'])['valide'])

    def test_merge_conflicting_copies_rejected_without_losing_history(self):
        f=self.f;f.pilot()
        with database(f.app.db_path) as conn:
            with self.assertRaisesRegex(ValueError,'Fusion impossible'):
                merge_pupils(conn,1,2)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM eleve').fetchone()[0],7)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])
