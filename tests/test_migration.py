from pathlib import Path
import sqlite3
import tempfile
import unittest
from moteur.db import init_db, database
from moteur.calcul import calculate_notes

LEGACY=Path(__file__).with_name('fixtures')/'schema_v1.sql'
class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'old.sqlite'
        conn=sqlite3.connect(self.db)
        try:
            conn.executescript(LEGACY.read_text(encoding='utf-8')+'''
            INSERT INTO eleve VALUES(1,'TMex',2,NULL,NULL);
            INSERT INTO sujet VALUES(1,'TMex',NULL,NULL,'Ancien sujet',NULL,NULL);
            INSERT INTO version VALUES(1,1,'A','Équation');
            INSERT INTO copie VALUES(1,1,1,1,'copie.pdf');
            INSERT INTO grille VALUES(1,1,1,'Grille',15);
            INSERT INTO exercice VALUES(1,1,'1',NULL,1);
            INSERT INTO question VALUES(1,1,'1',NULL,1);
            INSERT INTO item VALUES(1,1,'E1Q1I1','Résoudre',15,1,NULL);
            INSERT INTO correction VALUES(1,1,1,12,12,'Retour');
            INSERT INTO correction_item VALUES(1,1,1,12,'partiel',NULL,'Commentaire');
            INSERT INTO conseil VALUES(1,1,1,'Vérifier',1);
            ''')
            conn.commit()
        finally:
            conn.close()
    def test_preserves_rows_and_allows_review(self):
        init_db(self.db);init_db(self.db)
        with database(self.db) as conn:
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],2)
            self.assertEqual(conn.execute('SELECT points_obtenus FROM correction_item').fetchone()[0],12)
            self.assertEqual(conn.execute('SELECT texte FROM conseil').fetchone()[0],'Vérifier')
            self.assertEqual(conn.execute('SELECT grille_id FROM item').fetchone()[0],1)
        with self.assertRaises(ValueError):calculate_notes(self.db,1)
        with database(self.db) as conn:conn.execute('UPDATE grille SET valide=1 WHERE id=1')
        self.assertEqual(calculate_notes(self.db,1)['notes'][0]['note_finale'],12)
    def test_duplicate_legacy_copy_aborts_without_changes(self):
        conn=sqlite3.connect(self.db)
        try:
            conn.execute("INSERT INTO copie VALUES(2,1,1,1,'other.pdf')")
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(sqlite3.IntegrityError):init_db(self.db)
        conn=sqlite3.connect(self.db)
        try:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM copie').fetchone()[0],2)
            self.assertNotIn('grille_id',[r[1] for r in conn.execute('PRAGMA table_info(item)')])
            self.assertNotIn('valide',[r[1] for r in conn.execute('PRAGMA table_info(grille)')])
        finally:
            conn.close()
    def test_future_database_rejected(self):
        conn=sqlite3.connect(self.db)
        try:
            conn.execute('PRAGMA user_version=999')
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(ValueError):init_db(self.db)
