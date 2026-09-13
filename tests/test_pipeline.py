import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from moteur.db import database, init_db, SCHEMA
from moteur.import_evaluation import import_evaluation
from moteur.import_correction import import_correction, compatible_grid
from moteur.calcul import calculate, calculate_notes
from moteur.pipeline import run_pipeline, ai_packet
from moteur.render import export_results, tex_escape
from moteur.validation import load_json

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT/'examples/tmex_demo'

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root/'data.sqlite'
        init_db(self.db)
        self.evaluation = load_json(EXAMPLE/'evaluation.json')
    def import_eval(self, data=None):
        with database(self.db) as conn:
            return import_evaluation(data or self.evaluation, conn, EXAMPLE)
    def correction(self, conn, num=2):
        c = conn.execute('SELECT c.* FROM copie c JOIN eleve e ON e.id=c.eleve_id WHERE e.numero=?', (num,)).fetchone()
        return dict(load_json(EXAMPLE/f'correction_{num}.json'), copie_id=c['id'], grille_id=compatible_grid(conn,c))
    def corrected(self):
        sid=self.import_eval()
        with database(self.db) as conn:
            for num in (2,31,3): import_correction(self.correction(conn,num),conn)
        return sid
    def test_end_to_end_and_repeat(self):
        out=self.root/'exports'
        sid=run_pipeline(EXAMPLE/'pipeline.json',self.db,out)
        result=load_json(out/'notes.json')
        notes={r['numero']:r for r in result['notes']}
        self.assertEqual([notes[n]['note_finale'] for n in (2,31,3,22)],[16,18.5,13.5,None])
        self.assertEqual(notes[31]['note_brute'],30)
        self.assertEqual(notes[31]['note_individuelle'],15)
        self.assertEqual(len(list(out.glob('*.tex'))),4)
        self.assertEqual(len(list(out.glob('grille_*.md'))),2)
        self.assertIn('E1Q1I1',(out/'grille_1.md').read_text(encoding='utf-8'))
        tex=(out/'eleve_002.tex').read_text(encoding='utf-8')
        self.assertIn('2x+3=11', tex)
        self.assertIn('Ajouter la vérification', tex)
        run_pipeline(EXAMPLE/'pipeline.json', self.db,self.root/'second',replace=True)
        self.assertEqual((out/'notes.json').read_bytes(),(self.root/'second/notes.json').read_bytes())
        with database(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM sujet').fetchone()[0],1)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_evaluation_atomic_failure(self):
        self.evaluation['groupes'][0]['eleves'].append(99)
        with self.assertRaises(ValueError): self.import_eval()
        with database(self.db) as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM sujet').fetchone()[0],0)
    def test_reused_codes_other_evaluation(self):
        self.import_eval()
        self.evaluation['cle']='second'
        self.assertEqual(self.import_eval(),2)
    def test_reimport_key_conflict(self):
        self.import_eval()
        self.evaluation['sujet']['titre']='changed'
        with self.assertRaises(ValueError): self.import_eval()
    def test_invalid_evaluation(self):
        for mutate in (lambda d:d['grilles'][0].update(total_points=99),
                       lambda d:d['grilles'][0].update(version='Z'),
                       lambda d:d['eleves'].append({'numero':True}),
                       lambda d:d['groupes'].append({'numero':2,'eleves':[2]}),
                       lambda d:d['grilles'][0]['exercices'][0]['questions'][0]['items'][0].update(bareme_max=-1)):
            d=copy.deepcopy(self.evaluation); mutate(d)
            with self.assertRaises((ValueError,sqlite3.IntegrityError)): self.import_eval(d)
    def test_missing_pdf_check(self):
        with database(self.db) as c, self.assertRaises(ValueError):
            import_evaluation(self.evaluation,c,EXAMPLE,check_pdfs=True)
    def test_correction_validation_and_rollback(self):
        self.import_eval()
        mutations=[lambda d:d['items'].pop(),lambda d:d['items'].append(d['items'][0]),
                   lambda d:d['items'][0].update(points_obtenus=99),
                   lambda d:d['items'][0].update(points_obtenus=True),
                   lambda d:d['items'][0].update(points_obtenus=float('inf')),
                   lambda d:d['items'][0].update(item_code='foreign'),
                   lambda d:d['conseils'][0].update(item_code='foreign'),
                   lambda d:d['annotations'][0].update(x=.9,largeur=.5),
                   lambda d:d['annotations'][0].update(page=0),lambda d:d.update(note_finale=20)]
        for mutate in mutations:
            with database(self.db) as c: d=self.correction(c)
            mutate(d)
            with self.assertRaises(ValueError):
                with database(self.db) as c: import_correction(d,c)
            with database(self.db) as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM correction').fetchone()[0],0)
    def test_wrong_grid_and_absent(self):
        self.import_eval()
        with database(self.db) as c:
            d=self.correction(c)
            d['grille_id']=2
            with self.assertRaises(ValueError): import_correction(d,c)
            d=self.correction(c)
            d['copie_id']=c.execute("SELECT id FROM copie WHERE statut='absent'").fetchone()[0]
            with self.assertRaises(ValueError): import_correction(d,c)
    def test_unvalidated_grid(self):
        self.evaluation['grilles'][0]['validee']=False
        self.import_eval()
        with database(self.db) as c, self.assertRaises(ValueError): import_correction(self.correction(c),c)
    def test_failed_replacement_preserves_previous(self):
        self.corrected()
        with database(self.db) as c: d=self.correction(c)
        d['conseils'][0]['item_code']='foreign'
        with self.assertRaises(ValueError):
            with database(self.db) as c: import_correction(d,c,replace=True)
        self.assertEqual(calculate_notes(self.db,1)['notes'][0]['note_finale'],16)
    def test_raw_cache_not_authoritative(self):
        sid=self.corrected()
        with database(self.db) as c: c.execute('UPDATE correction SET note_brute=99,note_finale=99')
        self.assertEqual(calculate_notes(self.db,sid)['notes'][0]['note_brute'],12)
    def test_missing_correction_blocks_calculation(self):
        sid=self.import_eval()
        with self.assertRaisesRegex(ValueError,'non corrigée'): calculate_notes(self.db,sid)
    def test_missing_group_member_blocks_calculation(self):
        sid=self.corrected()
        with database(self.db) as c: c.execute("DELETE FROM copie WHERE statut='absent'")
        with self.assertRaisesRegex(ValueError,'sans copie'): calculate_notes(self.db,sid)
    def test_absence_zero(self):
        self.evaluation['sujet']['config_notes']['absences']['mode']='zero'
        sid=self.corrected()
        rows={r['numero']:r for r in calculate_notes(self.db,sid)['notes']}
        self.assertEqual(rows[2]['note_finale'],14.5)
        self.assertEqual(rows[22]['note_finale'],0)
    def test_group_modes_and_singleton(self):
        self.evaluation['sujet']['config_notes']['note_groupe']['mode']='moyenne_groupe'
        sid=self.corrected()
        self.assertEqual(calculate_notes(self.db,sid)['notes'][0]['note_groupe'],4)
        with database(self.db) as c:
            c.execute('DELETE FROM groupe_eleve')
            config={'note_groupe':{'sans_camarades':'individuelle'}}
            c.execute('UPDATE sujet SET config_notes=?',(json.dumps(config),))
        self.assertEqual(calculate_notes(self.db,sid)['notes'][0]['note_groupe'],4)
        with database(self.db) as c:
            c.execute('UPDATE sujet SET config_notes=?',(json.dumps({'note_groupe':{'sans_camarades':'erreur'}}),))
        with self.assertRaises(ValueError): calculate_notes(self.db,sid)
    def test_sql_constraints(self):
        self.import_eval()
        with database(self.db) as c:
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute('UPDATE item SET grille_id=2 WHERE id=1')
            import_correction(self.correction(c),c)
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute('UPDATE correction_item SET points_obtenus=100')
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute('UPDATE item SET bareme_max=100 WHERE id=1')
    def test_run_rolls_back_on_bad_later_file(self):
        manifest=load_json(EXAMPLE/'pipeline.json')
        manifest['evaluation']=str(EXAMPLE/'evaluation.json')
        manifest['corrections'][0]['file']=str(EXAMPLE/'correction_2.json')
        manifest['corrections'][1]['file']='missing.json'
        path=self.root/'pipeline.json';path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaises(OSError): run_pipeline(path,self.db,self.root/'out')
        with database(self.db) as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM sujet').fetchone()[0],0)
        self.assertFalse((self.root/'out').exists())
    def test_export_existing_directory_rejected(self):
        sid=self.corrected();out=self.root/'out';out.mkdir()
        with database(self.db) as c, self.assertRaises(ValueError): export_results(c,calculate(c,sid),out)
    def test_prepare_ai(self):
        self.import_eval()
        with database(self.db) as c: packet=ai_packet(c,1)
        self.assertEqual(len(packet['items']),3)
        self.assertIsNone(packet['reponse_structure']['items'][0]['points_obtenus'])
    def test_strict_json_and_escaping(self):
        p=self.root/'invalid.json'
        for value in ('{"x":1,"x":2}','{"x":NaN}'):
            p.write_text(value, encoding='utf-8')
            with self.assertRaises(ValueError):load_json(p)
        self.assertEqual(tex_escape('50% & x_1'),r'50\% \& x\_1')
    def test_packaged_schema_matches_documented(self):
        self.assertEqual(SCHEMA.read_bytes(),(ROOT/'db/schema.sql').read_bytes())
    def test_cli_error_exit(self):
        p=subprocess.run([sys.executable,'-m','moteur','calculate','--db',str(self.db),'--sujet','99'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(p.returncode,2);self.assertIn('Sujet inconnu',p.stderr)

    def test_compilation_failure_cleans_output_and_rolls_back(self):
        from unittest.mock import patch
        with patch('moteur.render.compile_pdf', side_effect=RuntimeError('LaTeX échoue')):
            with self.assertRaises(RuntimeError):
                run_pipeline(EXAMPLE/'pipeline.json',self.db,self.root/'failed-pdf',pdf=True)
        self.assertFalse((self.root/'failed-pdf').exists())
        self.assertFalse(list(self.root.glob('.smartcorrection-*')))
        with database(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM sujet').fetchone()[0],0)

    def test_second_group_never_contributes(self):
        self.evaluation['groupes']=[{'numero':1,'eleves':[2,31]}, {'numero':2,'eleves':[3,22]}]
        sid=self.corrected()
        rows={r['numero']:r for r in calculate_notes(self.db,sid)['notes']}
        self.assertEqual(rows[2]['note_groupe'],5)
        self.assertEqual(rows[3]['note_groupe'],0)
        self.assertEqual([p['numero'] for p in rows[2]['camarades']],[31])

    def test_partial_data_in_sql_is_not_treated_as_zero(self):
        sid=self.corrected()
        with database(self.db) as c:
            c.execute('DELETE FROM correction_item WHERE id=1')
        with self.assertRaisesRegex(ValueError,'incomplète'):
            calculate_notes(self.db,sid)
