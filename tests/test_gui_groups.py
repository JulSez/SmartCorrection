import csv
import io
import json
import os
import unittest
from pypdf import PdfReader
import test_gui
from moteur.gui_prompts import make_prompt


class GroupTests(unittest.TestCase):
    def setUp(self):
        self.f = test_gui.GuiWorkflowTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def groups(self, text, active=True):
        return self.f.app.groups(self.f.ident, active, text)

    def result(self, final=False, pdf=False):
        r = self.f.app.generate(self.f.ident, final=final, pdf=pdf)
        return r, json.loads(self.f.app.file('rendu',r['id'],'notes.json').read_text())

    def test_default_validation_and_revision_preservation(self):
        self.assertFalse(self.f.app.state(self.f.ident)['groupes']['actif'])
        g = self.groups('1, 2\n3 4;5')
        self.assertEqual(g['sans_groupe'], [6,7])
        for text in ('1,1', '1,2\n2,3', '99', 'Alice'):
            with self.assertRaises(ValueError):
                self.groups(text)
            self.assertEqual(self.f.app.state(self.f.ident)['groupes'],g)
        self.f.exchange('grille',self.f.grid)
        self.assertEqual(self.f.app.state(self.f.ident)['groupes'],g)
        for stage in ('ouverture','grille','copies','correction'):
            prompt = make_prompt(self.f.app,self.f.ident,stage)
            self.assertNotIn('Alice',prompt)
            self.assertNotIn('Alpha',prompt)

    def test_peer_average_excludes_self_absence_and_recomputes(self):
        self.groups('1,2,3,7\n4\n5,6')
        self.f.pilot()
        r,d = self.result()
        rows = {x['numero']:x for x in d['notes']}
        self.assertEqual(rows[1]['note_individuelle'],10)
        self.assertAlmostEqual(rows[1]['note_groupe'],10/3)
        self.assertEqual(rows[1]['note_finale'],13.5)
        self.assertIn('À traiter',rows[4]['etat_groupe'])
        self.assertIn('En attente',rows[5]['etat_groupe'])
        self.assertIsNone(rows[5]['note_finale'])
        correction=self.f.corrections(['C002'])
        correction['corrections'][0]['items'][0]['points_obtenus']=2
        self.f.exchange('correction',correction)
        _,d=self.result()
        rows={x['numero']:x for x in d['notes']}
        self.assertAlmostEqual(rows[1]['note_groupe'],25/6)
        self.assertAlmostEqual(rows[2]['note_groupe'],10/3)
        self.assertFalse(next(x for x in self.f.app.state(self.f.ident)['rendus'] if x['id']==r['id'])['valide'])
        self.groups('1,7\n2,3\n4,5,6')
        _,d=self.result()
        self.assertIn('aucun camarade',d['notes'][0]['etat_groupe'])
        self.groups('1,7\n2,3\n4,5,6',False)
        _,d=self.result()
        self.assertEqual(d['notes'][0]['note_finale'],13.5)

    def test_peers_outside_sample_and_final_csv(self):
        self.f.inventory['copies'][5]['numero']=6
        self.f.exchange('copies',self.f.inventory)
        self.groups('1,6\n2,3,4,5,7')
        self.f.pilot()
        _,d=self.result()
        self.assertIsNone(d['notes'][0]['note_finale'])
        self.f.exchange('correction',self.f.corrections(['C006']))
        r,d=self.result(final=True)
        self.assertAlmostEqual(next(x for x in d['notes'] if x['numero']==1)['note_groupe'],10/3)
        csv_text=self.f.app.file('rendu',r['id'],'notes.csv').read_text(encoding='utf-8-sig')
        row=next(x for x in csv.DictReader(io.StringIO(csv_text),delimiter=';') if x['numero']=='1')
        self.assertEqual(float(row['note_individuelle']),10)
        self.assertAlmostEqual(float(row['note_groupe']),10/3)
        self.assertEqual(float(row['note_finale']),13.5)
        self.assertIn('etat_groupe',row)
        self.f.exchange('correction',{'corrections':[], 'a_revoir':[{'reference':'C006','motif':'Relire le raisonnement'}]})
        _,pending=self.result()
        self.assertIsNone(pending['notes'][0]['note_groupe'])
        self.groups('1,2\n3,4,5,6,7')
        self.assertFalse(self.f.app.state(self.f.ident)['dossier']['termine'])
        self.assertFalse(self.f.app.state(self.f.ident)['rendus'][0]['valide'])

    @unittest.skipUnless(os.environ.get('SMARTCORRECTION_TEST_PDF')=='1','real PDF test')
    def test_pdf_three_columns_and_pending(self):
        self.groups('1,2,3,7\n4\n5,6')
        self.f.pilot()
        r,d=self.result(pdf=True)
        path=self.f.app.file('rendu',r['id'],'corrections.pdf')
        reader=PdfReader(path)
        text='\n'.join(p.extract_text() for p in reader.pages)
        for label in ('Individuelle /15','Groupe /5','Finale /20','En attente','traiter','Corrigé'):
            self.assertIn(label,text)
        for page in reader.pages:
            self.assertAlmostEqual(float(page.mediabox.width),210*72/25.4,places=2)
        if os.environ.get('SC_REVIEW_PDF'):
            import shutil
            shutil.copyfile(path,os.environ['SC_REVIEW_PDF'])
