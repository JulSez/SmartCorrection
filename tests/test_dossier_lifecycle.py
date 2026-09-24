import unittest
from unittest.mock import patch
from pathlib import Path
from moteur.db import database
from moteur.gui import dispatch
import test_gui

class DossierLifecycleTests(unittest.TestCase):
    def setUp(self):
        case=test_gui.GuiWorkflowTests(); case.setUp(); self.addCleanup(case.doCleanups)
        case.pilot(); self.case=case; self.app=case.app; self.ident=case.ident
        self.other=self.app.create('TEST','Autre épreuve')['id']

    def test_delete_removes_only_this_dossier_and_its_files(self):
        rendered=self.app.generate(self.ident,pdf=False)
        source=self.app.file('source',self.case.source['id'])
        folder=self.app.file('rendu',rendered['id'],'notes.json').parent
        with database(self.app.db_path) as conn:
            pupils=conn.execute('SELECT COUNT(*) FROM eleve').fetchone()[0]
            policies=conn.execute('SELECT COUNT(*) FROM consigne_revision').fetchone()[0]
        result=dispatch(self.app,{'action':'supprimer','dossier':self.ident,'confirmer':True})
        self.assertTrue(result['supprime']); self.assertEqual(result['avertissements'],[])
        self.assertFalse(source.exists()); self.assertFalse(folder.exists())
        self.assertEqual([d['id'] for d in self.app.home()['dossiers']],[self.other])
        with database(self.app.db_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM eleve').fetchone()[0],pupils)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM consigne_revision').fetchone()[0],policies)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM correction').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM sujet').fetchone()[0],0)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_confirmation_and_locked_files_preserve_the_dossier(self):
        for value in (None,False,'true',1):
            with self.assertRaises(ValueError): self.app.delete(self.ident,value)
        with patch.object(Path,'rename',side_effect=PermissionError('PDF ouvert')):
            with self.assertRaises(PermissionError): self.app.delete(self.ident,True)
        self.assertEqual(self.app.state(self.ident)['dossier']['id'],self.ident)
        self.assertTrue(self.app.file('source',self.case.source['id']).exists())

    def test_database_failure_restores_moved_files(self):
        with database(self.app.db_path) as conn:
            conn.execute("CREATE TRIGGER refuse_delete BEFORE DELETE ON ui_dossier BEGIN SELECT RAISE(ABORT, 'refus'); END")
        with self.assertRaises(Exception): self.app.delete(self.ident,True)
        self.assertTrue(self.app.file('source',self.case.source['id']).exists())
        self.assertTrue(self.app.state(self.ident)['copies'])

    def test_archive_is_reversible_and_survives_reopening(self):
        from moteur.gui_service import Application
        before=self.app.state(self.ident)
        dispatch(self.app,{'action':'archiver','dossier':self.ident,'actif':True})
        reopened=Application(self.app.db_path,self.app.data_dir,self.case.root/'legacy')
        row=next(d for d in reopened.home()['dossiers'] if d['id']==self.ident)
        self.assertTrue(row['archive'])
        self.assertEqual(reopened.state(self.ident),before)
        reopened.archive(self.ident,False)
        self.assertFalse(next(d for d in reopened.home()['dossiers'] if d['id']==self.ident)['archive'])
        reopened.archive(self.ident,True)
        reopened.delete(self.ident,True)
        with database(reopened.db_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM ui_archive').fetchone()[0],0)

    def test_archive_rejects_invalid_or_missing_ids(self):
        with self.assertRaises(ValueError): self.app.archive(self.ident,'true')
        with self.assertRaises(ValueError): self.app.archive('missing',True)

    def test_delete_also_removes_previous_grid_revisions(self):
        self.case.exchange('grille',self.case.grid)
        with database(self.app.db_path) as conn:
            self.assertGreater(conn.execute('SELECT COUNT(*) FROM sujet').fetchone()[0],1)
        self.app.delete(self.ident,True)
        with database(self.app.db_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM sujet').fetchone()[0],0)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])
