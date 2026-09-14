"""Real LaTeX compilation, enabled in the dedicated PDF CI job."""
import os
import json
import unittest
from pypdf import PdfReader
from moteur.notes import config_from_mapping
from moteur.render import compile_pdf, render_student
import test_gui


@unittest.skipUnless(os.environ.get('SMARTCORRECTION_TEST_PDF') == '1', 'PDF integration runs in the dedicated LaTeX job')
class GuiPdfTests(unittest.TestCase):
    def test_score_tables_compile_without_array_m_column_helper(self):
        fixture = test_gui.GuiWorkflowTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.pilot()
        for grouped in (False, True):
            with self.subTest(grouped=grouped):
                fixture.app.groups(fixture.ident, grouped, '1,2,3,4,5,6,7')
                result = fixture.app.generate(fixture.ident, pdf=False)
                data = json.loads(fixture.app.file('rendu', result['id'], 'notes.json').read_text())
                source = render_student(data['fiches'][0], data['sujet'], config_from_mapping(data['config']))
                self.assertNotIn('m{', source)
                # Exercise an array installation where its m-column helper is unavailable.
                source = source.replace(r'\begin{document}', r'\makeatletter\let\ar@align@mcell\undefined\makeatother\begin{document}')
                tex = fixture.root / ('table-groupe.tex' if grouped else 'table-individuelle.tex')
                tex.write_text(source, encoding='utf-8')
                pdf = PdfReader(compile_pdf(tex))
                self.assertGreaterEqual(len(pdf.pages), 1)

    def test_longtable_tables_compile_without_colortbl(self):
        fixture = test_gui.GuiWorkflowTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.pilot()
        for grouped in (False, True):
            with self.subTest(grouped=grouped):
                fixture.app.groups(fixture.ident, grouped, '1,2,3,4,5,6,7')
                result = fixture.app.generate(fixture.ident, pdf=False)
                data = json.loads(fixture.app.file('rendu', result['id'], 'notes.json').read_text())
                source = render_student(data['fiches'][0], data['sujet'], config_from_mapping(data['config']))
                self.assertIn(r'\usepackage{xcolor}', source)
                self.assertIn(r'\begin{longtable}', source)
                self.assertNotIn(r'\usepackage[table]{xcolor}', source)
                self.assertNotIn(r'\rowcolor', source)
                self.assertNotIn(r'\arrayrulecolor', source)
                self.assertNotIn('insert@pcolumn', source)
                self.assertIn(data['fiches'][0]['corrige_latex'], source)
                tex = fixture.root / ('longtable-groupe.tex' if grouped else 'longtable-individuelle.tex')
                tex.write_text(source, encoding='utf-8')
                pdf = PdfReader(compile_pdf(tex))
                self.assertGreaterEqual(len(pdf.pages), 1)
                log = (fixture.root / (tex.stem + '.a6.log')).read_text(encoding='utf-8', errors='replace')
                self.assertNotIn('colortbl.sty', log)
                self.assertIn('Conseils', '\n'.join(p.extract_text() for p in pdf.pages))

    def test_final_pdf_skips_a_broken_copy_and_can_restore_it(self):
        fixture = test_gui.GuiWorkflowTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        # A second version is used by only one copy; its raw LaTeX cannot compile.
        fixture.grid['versions'].append({'version': 'B'})
        grid_b = dict(fixture.grid['grilles'][0], nom='Version B', version='B')
        fixture.grid['grilles'].append(grid_b)
        fixture.exchange('grille', fixture.grid)
        fixture.app.corrige(fixture.ident, 'A', r'Corrigé valide : $x=2$.', True)
        fixture.app.corrige(fixture.ident, 'B', r'\CommandeInconnueSmartCorrection', True)
        fixture.inventory['copies'][5]['version'] = 'B'
        fixture.exchange('copies', fixture.inventory)
        fixture.pilot()
        fixture.exchange('correction', fixture.corrections(['C006']))
        exported = fixture.app.generate(fixture.ident, final=True, pdf=False)
        data = json.loads(fixture.app.file('rendu', exported['id'], 'notes.json').read_text())
        bad = next(s for s in data['fiches'] if s['version']=='B')
        tex = fixture.root/'broken.tex'
        tex.write_text(render_student(bad, data['sujet'], config_from_mapping(data['config'])), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'Compilation échouée : broken.tex'):
            compile_pdf(tex)
        fixture.app.include_in_final(fixture.ident, 'C006', False)
        final = fixture.app.generate(fixture.ident, final=True, pdf=True)
        pdf = PdfReader(fixture.app.file('rendu', final['id'], 'corrections.pdf'))
        self.assertEqual(len(pdf.pages), 6)
        self.assertNotIn('C006', '\n'.join(p.extract_text() for p in pdf.pages))
        fixture.app.include_in_final(fixture.ident, 'C006', True)
        # The original correction is retained; after repair it can be included again.
        fixture.app.corrige(fixture.ident, 'B', r'Corrigé réparé : $x=2$.', True)
        fixture.app.review(fixture.ident, 'C006')
        fixture.app.sample(fixture.ident, [f'C{i:03d}' for i in range(1, 6)], True)
        restored = fixture.app.generate(fixture.ident, final=True, pdf=True)
        pdf = PdfReader(fixture.app.file('rendu', restored['id'], 'corrections.pdf'))
        self.assertEqual(len(pdf.pages), 7)
        self.assertIn('C006', '\n'.join(p.extract_text() for p in pdf.pages))

    def test_fiches_and_combined_document(self):
        fixture = test_gui.GuiWorkflowTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.pilot()
        fixture.exchange('correction', fixture.corrections(['C006']))
        result = fixture.app.generate(fixture.ident, final=True, pdf=True)
        pdf = PdfReader(fixture.app.file('rendu', result['id'], 'corrections.pdf'))
        self.assertEqual(len(pdf.pages), 7, result['fichiers'])
        for page in pdf.pages:
            self.assertAlmostEqual(float(page.mediabox.width), 210*72/25.4, places=2)
            self.assertAlmostEqual(float(page.mediabox.height), 148*72/25.4, places=2)
        texts = [page.extract_text() for page in pdf.pages]
        self.assertIn('13,5', texts[1])
        self.assertTrue(any('C006' in text for text in texts))
        self.assertTrue(any('Absence' in text for text in texts))
        self.assertIn('Conseils', texts[1])
        self.assertIn('Corrigé', texts[1])

    def test_long_sides_keep_their_position_and_all_content(self):
        fixture = test_gui.GuiWorkflowTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.pilot()
        result = fixture.app.generate(fixture.ident, pdf=False)
        data = json.loads(fixture.app.file('rendu', result['id'], 'notes.json').read_text())
        # Exercise both asymmetric cases: longer marking table, then longer reference.
        for count, paragraphs in ((35, 1), (2, 45)):
            with self.subTest(items=count, reference_paragraphs=paragraphs):
                student = dict(data['fiches'][0])
                student['items'] = [dict(student['items'][0], question=str(i+1),
                    description=f'CRITERE{i:03d} - Résoudre et justifier.',
                    commentaire=f'RETOUR{i:03d} - Vérifier le signe.') for i in range(count)]
                student['conseils'] = [{'texte': 'FINCONSEILS - Relire chaque étape.'}]
                student['corrige_latex'] = '\n\n'.join(
                    f'REFERENCE{i:03d}. On isole la variable, puis on vérifie la solution dans l’équation initiale. '
                    r'\[2x+3=7 \iff x=2.\]' for i in range(paragraphs)) + '\n\nFINCORRIGE.'
                tex = fixture.root/f'long-{count}-{paragraphs}.tex'
                tex.write_text(render_student(student, data['sujet'], config_from_mapping(data['config'])))
                pdf = PdfReader(compile_pdf(tex))
                self.assertGreater(len(pdf.pages), 1)
                all_text = '\n'.join(page.extract_text() for page in pdf.pages)
                for marker in [*(f'CRITERE{i:03d}' for i in range(count)),
                               *(f'RETOUR{i:03d}' for i in range(count)),
                               *(f'REFERENCE{i:03d}' for i in range(paragraphs)), 'FINCONSEILS', 'FINCORRIGE']:
                    self.assertEqual(all_text.count(marker), 1, marker)
                for page in pdf.pages:
                    self.assertAlmostEqual(float(page.mediabox.width), 210*72/25.4, places=2)
                    def check_side(text, cm, tm, font, size):
                        x = tm[4]*cm[0] + tm[5]*cm[2] + cm[4]
                        if any(marker in text for marker in ('CRITERE', 'RETOUR', 'FINCONSEILS')):
                            self.assertLess(x, 105*72/25.4, text)
                        if any(marker in text for marker in ('REFERENCE', 'FINCORRIGE')):
                            self.assertGreaterEqual(x, 105*72/25.4, text)
                    page.extract_text(visitor_text=check_side)

    def test_unicode_prose_compiles_without_changing_raw_latex(self):
        fixture = test_gui.GuiWorkflowTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.pilot()
        result = fixture.app.generate(fixture.ident, pdf=False)
        data = json.loads(fixture.app.file('rendu', result['id'], 'notes.json').read_text())
        for case, prose in (
            ('minus', 'Une fois x=−sqrt(6) obtenu, ne transforme pas sqrt(6) en 3.'),
            ('symbols', '− × √ ≤ ≥ ≠ → ⇔ ∞ ; α β π ℝ ∈ ∅ ; x² x₁ ; 50% & coût 5€ ; 🙂'),
        ):
            with self.subTest(case=case):
                student = dict(data['fiches'][0], numero=26, label='n° 26 - Élève fictif')
                student['items'] = [dict(student['items'][0], description=prose,
                                         commentaire=prose, annotation=prose)]
                student['commentaire_global'] = prose
                student['annotations'] = [{'page': 1, 'item_code': 'E1Q1I1', 'texte': prose}]
                student['conseils'] = [{'texte': prose}]
                raw = r'\begin{align*}x&=-\sqrt{6}\\x^2&=6\end{align*}'
                student['corrige_latex'] = raw
                source = render_student(student, data['sujet'], config_from_mapping(data['config']))
                self.assertIn(raw, source)
                self.assertNotIn('−', source)
                folder = fixture.root/case
                folder.mkdir()
                tex = folder/'eleve_026.tex'
                tex.write_text(source, encoding='utf-8')
                pdf = PdfReader(compile_pdf(tex))
                self.assertGreaterEqual(len(pdf.pages), 1)
                self.assertTrue(any('Conseils' in page.extract_text() for page in pdf.pages))
