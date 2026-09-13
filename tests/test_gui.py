"""User workflow and transaction boundaries, with a small synthetic math evaluation."""
import base64
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from pypdf import PdfWriter
from moteur.calcul import calculate_notes
from moteur.db import database
from moteur.gui import make_server
from moteur.gui_prompts import make_prompt
from moteur.gui_service import Application, response_body


class GuiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = Application(self.root/'db.sqlite', self.root/'data', self.root/'legacy')
        self.app.roster('TEST', 'nom;prenom\nAlpha;Alice\nBeta;Benoît\nGamma;Chloé\nDelta;David\nEpsilon;Emma\nZeta;Farid\nEta;Gina\n', True)
        self.ident = self.app.create('TEST', 'Équations — démonstration')['id']
        writer = PdfWriter()
        for _ in range(7):
            writer.add_blank_page(width=595, height=842)
        raw = io.BytesIO(); writer.write(raw)
        self.source = self.app.upload(self.ident, 'paquet', 'copies.pdf', base64.b64encode(raw.getvalue()).decode())
        self.grid = dict(versions=[{'version': 'A'}], grilles=[{
            'nom': 'Équation', 'version': 'A', 'exercices': [{'numero': '1', 'questions': [{'numero': '1', 'items': [
                {'code': 'E1Q1I1', 'description': 'Résoudre l’équation', 'bareme_max': 2},
                {'code': 'E1Q1I2', 'description': 'Conclure', 'bareme_max': 1},
            ]}]}]}])
        self.exchange('grille', self.grid)
        self.app.corrige(self.ident, 'A', r'\section*{Équation}\begin{align*}2x+3&=7\\2x&=4\\x&=2\end{align*}Ainsi, $S=\{2\}$.', True)
        self.inventory = {'copies': [{'reference': f'C{i:03d}', 'numero': i if i < 6 else None, 'version': 'A', 'pages': [i]} for i in range(1,7)], 'pages_ignorees': [{'page': 7, 'motif': 'Page blanche'}], 'absents': [7]}
        self.exchange('copies', self.inventory)

    def envelope(self, value):
        return dict(value, dossier=self.ident, revision=self.app.state(self.ident)['dossier']['revision'])

    def exchange(self, stage, value, commit=True):
        return self.app.exchange(self.ident, stage, json.dumps(self.envelope(value), ensure_ascii=False), commit)

    def corrections(self, refs):
        return {'corrections': [{'reference': ref, 'items': [
            {'item_code': 'E1Q1I1', 'points_obtenus': 1, 'commentaire': 'Une erreur de signe dans la dernière égalité.'},
            {'item_code': 'E1Q1I2', 'points_obtenus': 1}],
            'conseils': [{'item_code': 'E1Q1I1', 'texte': 'Vérifier la solution dans l’équation initiale.'}]
        } for ref in refs]}

    def pilot(self):
        refs = [f'C{i:03d}' for i in range(1,6)]
        self.exchange('correction', self.corrections(refs))
        self.app.sample(self.ident, refs, True)

    def finish(self):
        self.pilot()
        self.exchange('correction', self.corrections(['C006']))
        return self.app.generate(self.ident, final=True, pdf=False)

    def test_workflow_partial_preview_final_and_rewritten_instructions(self):
        self.pilot()
        preview = self.app.generate(self.ident, pdf=False)
        notes = json.loads(self.app.file('rendu', preview['id'], 'notes.json').read_text())
        self.assertEqual(len(notes['notes']), 5)
        self.assertEqual(notes['notes'][0]['note_finale'], 13.5)
        prompt = make_prompt(self.app, self.ident, 'correction', mode='reste')
        self.assertIn('C006', prompt)
        self.assertNotIn('"reference": "C001"', prompt)
        with self.assertRaisesRegex(ValueError, 'non corrigée'):
            self.app.generate(self.ident, final=True, pdf=False)
        self.exchange('correction', self.corrections(['C006']))
        rendered = self.app.generate(self.ident, final=True, pdf=False)
        notes = json.loads(self.app.file('rendu', rendered['id'], 'notes.json').read_text())
        self.assertEqual(len(notes['notes']), 7)
        self.assertEqual(sum(n['statut']=='absent' for n in notes['notes']), 1)
        self.assertIn('C006', next(n for n in notes['notes'] if n['numero'] is None)['label'])
        for n in notes['notes']:
            self.assertFalse(n['camarades'])
        feedback = {'base_generale': None, 'base_classe': None, 'generales': 'Ne pas pénaliser deux fois la même erreur.', 'classe': 'Exiger une phrase de conclusion.'}
        self.exchange('retour', feedback, False)
        self.assertEqual(self.app.instruction_history('TEST'), [])
        self.exchange('retour', feedback)
        with self.assertRaisesRegex(ValueError, 'mises à jour'):
            self.exchange('retour', feedback)
        second = self.app.create('TEST', 'Prochaine évaluation')['id']
        self.assertIn(feedback['generales'], make_prompt(self.app, second, 'ouverture'))
        self.assertIn(feedback['classe'], make_prompt(self.app, second, 'ouverture'))
        self.assertNotIn(feedback['classe'], make_prompt(self.app, self.ident, 'ouverture'))
        self.assertEqual(len(self.app.instruction_history('TEST')), 2)

    def test_whole_response_is_rolled_back_if_one_copy_invalid(self):
        self.exchange('correction', self.corrections(['C001']))
        bad = self.corrections(['C001','C002'])
        bad['corrections'][0]['items'][0]['points_obtenus'] = 2
        bad['corrections'][1]['items'][0]['points_obtenus'] = 3
        with self.assertRaisesRegex(ValueError, 'supérieurs'):
            self.exchange('correction', bad)
        with database(self.app.db_path) as conn:
            rows = conn.execute('SELECT note_brute FROM correction').fetchall()
            self.assertEqual([r[0] for r in rows], [2])

    def test_preview_is_read_only_and_drafts_survive_restart(self):
        response = self.corrections(['C001'])
        self.exchange('correction', response, False)
        self.assertFalse(any(c['correction_id'] for c in self.app.state(self.ident)['copies']))
        self.app.draft(self.ident, 'correction', json.dumps(response))
        app = Application(self.app.db_path, self.app.data_dir, self.root/'legacy')
        self.assertEqual(app.state(self.ident)['brouillons']['correction'], json.dumps(response))
        self.exchange('correction', response)
        self.assertNotIn('correction', self.app.state(self.ident)['brouillons'])

    def test_grid_revision_archives_grades_and_rejects_old_response(self):
        self.pilot()
        old = json.dumps(self.envelope(self.corrections(['C001'])))
        before = self.app.state(self.ident)
        self.exchange('grille', self.grid)
        after = self.app.state(self.ident)
        self.assertEqual(after['dossier']['revision'], 2)
        self.assertFalse(after['dossier']['echantillon_valide'])
        self.assertFalse(any(c['correction_id'] for c in after['copies']))
        self.assertEqual([c['reference'] for c in before['copies']], [c['reference'] for c in after['copies']])
        with database(self.app.db_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM correction').fetchone()[0], 5)
        with self.assertRaisesRegex(ValueError, 'ancienne grille'):
            self.app.exchange(self.ident, 'correction', old, True)

    def test_inventory_page_validation_and_late_anonymous_attribution(self):
        bad = json.loads(json.dumps(self.inventory))
        bad['copies'][1]['pages'] = [1]
        with self.assertRaisesRegex(ValueError, 'deux fois'):
            self.exchange('copies', bad)
        bad = dict(self.inventory, pages_ignorees=[])
        with self.assertRaisesRegex(ValueError, 'non affectées'):
            self.exchange('copies', bad)
        self.finish()
        self.inventory['copies'][-1]['numero'] = 6
        self.exchange('copies', self.inventory)
        copy = next(c for c in self.app.state(self.ident)['copies'] if c['reference']=='C006')
        self.assertEqual(copy['numero'], 6)
        self.assertTrue(copy['correction_id'])

    def test_deductions_and_annotation_pages_are_validated(self):
        data = self.corrections(['C001'])
        del data['corrections'][0]['items'][0]['commentaire']
        with self.assertRaisesRegex(ValueError, 'expliquer'):
            self.exchange('correction', data)
        data = self.corrections(['C001'])
        data['corrections'][0]['annotations'] = [{'item_code': 'E1Q1I1', 'page': 2, 'texte': 'Erreur de signe'}]
        with self.assertRaisesRegex(ValueError, 'extérieure'):
            self.exchange('correction', data)
        data['corrections'][0]['annotations'][0]['page'] = 1
        self.exchange('correction', data)

    def test_incomplete_or_flagged_copy_blocks_approval_and_render(self):
        with self.assertRaisesRegex(ValueError, 'échantillon'):
            self.exchange('correction', self.corrections(['C006']))
        with self.assertRaisesRegex(ValueError, 'corrigée'):
            self.app.sample(self.ident, [f'C{i:03d}' for i in range(1,6)], True)
        self.pilot()
        self.exchange('correction', {'corrections': [], 'a_revoir': [{'reference': 'C001', 'motif': 'Passage illisible'}]})
        self.assertFalse(self.app.state(self.ident)['dossier']['echantillon_valide'])
        with self.assertRaisesRegex(ValueError, 'revoir'):
            self.app.generate(self.ident, pdf=False)

    def test_reference_change_requires_review_and_invalidates_documents(self):
        self.finish()
        self.app.corrige(self.ident, 'A', 'Nouveau corrigé vérifié.', True)
        state = self.app.state(self.ident)
        self.assertFalse(state['dossier']['termine'])
        self.assertFalse(state['dossier']['echantillon_valide'])
        self.assertTrue(all(not r['valide'] for r in state['rendus']))
        self.assertTrue(all(c['a_revoir'] for c in state['copies'] if c['statut']=='present'))
        self.app.review(self.ident, 'C001')
        self.assertIsNone(next(c for c in self.app.state(self.ident)['copies'] if c['reference']=='C001')['a_revoir'])

    def test_cli_still_requires_identification_of_every_copy(self):
        self.finish()
        with self.assertRaisesRegex(ValueError, 'non attribuée'):
            calculate_notes(self.app.db_path, self.app.state(self.ident)['dossier']['sujet_id'])

    def test_legacy_markdown_is_imported_once_without_overwriting_sqlite(self):
        legacy = self.root/'legacy'; legacy.mkdir()
        (legacy/'TEST.md').write_text('Tolérance historique.', encoding='utf-8')
        db = self.root/'legacy.sqlite'
        app = Application(db, self.root/'legacy-data', legacy)
        self.assertEqual(app.instruction_history('TEST')[0]['texte'], 'Tolérance historique.')
        (legacy/'TEST.md').write_text('Modification ignorée.', encoding='utf-8')
        app = Application(db, self.root/'legacy-data', legacy)
        self.assertEqual(app.instruction_history('TEST')[0]['texte'], 'Tolérance historique.')

    def test_prompts_have_a_fixed_machine_contract(self):
        prompt = make_prompt(self.app, self.ident, 'grille')
        self.assertIn('BLOC TECHNIQUE FIXE', prompt)
        self.assertIn('un unique bloc de code ```json', prompt)
        self.assertIn('objet JSON valide', prompt)
        latex = make_prompt(self.app, self.ident, 'corrige', 'A')
        self.assertIn('Rends uniquement le corps LaTeX', latex)
        self.assertIn('un unique bloc de code ```latex', latex)
        self.assertIn('sans \\documentclass', latex)
        self.assertIn('plusieurs pages', latex)
        self.finish()
        for stage in ('ouverture', 'grille', 'copies', 'correction', 'retour'):
            with self.subTest(stage=stage):
                text = make_prompt(self.app, self.ident, stage)
                self.assertIn('un unique bloc de code ```json', text)
                self.assertNotIn('sans bloc Markdown', text)
                self.assertNotIn('sans balises Markdown', text)

    def test_prompts_do_not_include_roster_or_filenames(self):
        self.finish()
        with database(self.app.db_path) as conn:
            conn.execute('UPDATE ui_fichier SET nom=? WHERE id=?', ('Alice_Alpha_copies.pdf', self.source['id']))
            conn.execute('UPDATE eleve SET numero=424242 WHERE classe=? AND numero=1', ('TEST',))
            conn.execute('UPDATE ui_copie SET a_revoir=? WHERE reference=?', ('Alice Alpha à vérifier', 'C001'))
        for stage in ('ouverture', 'grille', 'corrige', 'copies', 'correction', 'retour'):
            with self.subTest(stage=stage):
                text = make_prompt(self.app, self.ident, stage, version='A')
                for pupil in self.app.state(self.ident)['eleves']:
                    self.assertNotIn(pupil['nom'], text)
                    self.assertNotIn(pupil['prenom'], text)
                self.assertNotIn('424242', text)
                self.assertNotIn('Alice_Alpha_copies.pdf', text)
        self.assertIn('numero:null', make_prompt(self.app, self.ident, 'copies'))
        self.assertIn('C001', make_prompt(self.app, self.ident, 'correction'))

    def test_code_blocks_import_and_preview_without_weakening_json_validation(self):
        raw = json.dumps(self.envelope(self.corrections(['C001'])))
        block = '```json\n' + raw + '\n```'
        self.app.exchange(self.ident, 'correction', block, False)
        self.assertFalse(any(c['correction_id'] for c in self.app.state(self.ident)['copies']))
        self.app.exchange(self.ident, 'correction', block, True)
        self.assertTrue(next(c for c in self.app.state(self.ident)['copies'] if c['reference'] == 'C001')['correction_id'])
        for content in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1,}'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.app.exchange(self.ident, 'correction', '```json\n' + content + '\n```', True)

    def test_code_block_boundaries_are_strict(self):
        self.assertEqual(response_body('  ```JSON\r\n{}\r\n```\n', 'json'), '{}')
        self.assertEqual(response_body('```\n{}\n```', 'json'), '{}')
        self.assertEqual(response_body('```tex\nTexte.\n```', 'latex'), 'Texte.')
        for text in ('Voici :\n```json\n{}\n```', '```json\n{}\n```\nSuite',
                     '```json\n{}', '```python\n{}\n```', '```json\n{}\n```\n```json\n{}\n```'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                response_body(text, 'json')
        with self.assertRaisesRegex(ValueError, 'préambule'):
            self.app.corrige(self.ident, 'A', '```latex\n'+r'\documentclass{article}'+'\n```', True)

    def test_long_reference_is_preserved_in_drafts_database_prompts_and_exports(self):
        text = ('Démonstration détaillée. $2x+3=7$.\n\n' * 7000) + 'FIN DU CORRIGÉ.'
        self.assertGreater(len(text), 200000)
        self.app.draft(self.ident, 'corrige:A', text)
        app = Application(self.app.db_path, self.app.data_dir, self.root/'legacy')
        self.assertEqual(app.state(self.ident)['brouillons']['corrige:A'], text)
        result = app.corrige(self.ident, 'A', '```latex\n' + text + '\n```', True)
        self.assertEqual(result['caracteres'], len(text))
        self.assertEqual(app.state(self.ident)['versions'][0]['corrige_latex'], text)
        self.assertNotIn('corrige:A', app.state(self.ident)['brouillons'])
        self.exchange('correction', self.corrections(['C001']))
        app.sample(self.ident, ['C001'])
        self.assertIn('FIN DU CORRIGÉ.', make_prompt(app, self.ident, 'correction'))
        result = app.generate(self.ident, pdf=False)
        self.assertIn(text, app.file('rendu', result['id'], 'eleve_001.tex').read_text())

    def test_http_origin_token_and_file_boundaries(self):
        server = make_server(self.app)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join()))
        url = f'http://127.0.0.1:{server.server_port}'
        response = urllib.request.urlopen(url)
        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        html = response.read().decode()
        pdf_response = urllib.request.urlopen(url+'/file?kind=source&id='+self.source['id'])
        self.assertEqual(pdf_response.headers['Content-Type'], 'application/pdf')
        self.assertIn("frame-ancestors 'self'", pdf_response.headers['Content-Security-Policy'])
        self.assertNotIn("frame-ancestors 'none'", pdf_response.headers['Content-Security-Policy'])
        self.assertTrue(pdf_response.read().startswith(b'%PDF-'))
        external = urllib.request.Request(url+'/file?kind=source&id='+self.source['id'],
                                         headers={'Origin': 'https://external.invalid'})
        with self.assertRaises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(external)
        self.assertEqual(denied.exception.code, 403)
        token = html.split('name="csrf-token" content="')[1].split('"')[0]
        data = json.dumps({'action': 'creer', 'classe': 'TEST', 'titre': 'Deuxième'}).encode()
        for headers in ({}, {'X-SmartCorrection-Token': token, 'Origin': 'https://external.invalid'}):
            req = urllib.request.Request(url+'/api/action', data=data, headers=dict(headers, **{'Content-Type': 'application/json'}))
            with self.assertRaises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(req)
            self.assertEqual(exc.exception.code, 403)
        req = urllib.request.Request(url+'/api/action', data=data, headers={'Content-Type': 'application/json', 'X-SmartCorrection-Token': token})
        self.assertIn('id', json.load(urllib.request.urlopen(req)))
        from unittest.mock import patch
        for action,error,reparable in (
            ('generer', PermissionError('Dossier verrouillé'), False),
            ('echange', PermissionError('Dossier verrouillé'), False),
            ('echange', ValueError('JSON invalide'), True),
        ):
            with self.subTest(action=action,error=type(error).__name__):
                data=json.dumps({'action':action,'dossier':self.ident,'etape':'grille','texte':'{}'}).encode()
                req=urllib.request.Request(url+'/api/action',data=data,headers={'Content-Type':'application/json','X-SmartCorrection-Token':token})
                with patch.object(self.app,'generate' if action=='generer' else 'exchange',side_effect=error):
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(req)
                message=json.load(caught.exception)
                self.assertEqual(message['reponse_reparable'],reparable)
                if isinstance(error,PermissionError):
                    self.assertIn('pas auprès de l’IA',message['erreur'])
        self.assertEqual(urllib.request.urlopen(url+'/app.js').status, 200)
        with self.assertRaises(ValueError):
            self.app.file('rendu', 'unknown', '../../db.sqlite')


if __name__ == '__main__':
    unittest.main()
