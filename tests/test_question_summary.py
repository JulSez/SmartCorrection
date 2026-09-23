import copy
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from moteur.notes import config_from_mapping
from moteur.render import question_summary, render_student, compile_pdf


def fixture():
    items = []
    for q in range(1, 7):
        for i, (points, maximum, error) in enumerate([
            (.25, .75, 'Erreur de signe.'), (.125, .25, 'Équivalences manquantes.'),
            (.25, .25, 'Bravo, tout est juste.')]):
            items.append(dict(code=f'Q{q}I{i}', exercice='1', question=str(q),
                              description='Critère machine', points_obtenus=points,
                              bareme_max=maximum, commentaire=error, annotation=error))
    return dict(label='Copie C001', statut='present', note_finale=10,
                items=items, annotations=[{'item_code':'Q1I0','texte':'Erreur de signe.'}],
                corrige_latex=r'\begin{align*}2x&=4\\x&=2\end{align*}')


def config():
    return config_from_mapping({'note_groupe': {'mode':'aucun', 'max':0},
                                'note_individuelle':{'max':20}, 'note_finale':{'max':20}})


class QuestionSummaryTests(unittest.TestCase):
    def test_subtotals_errors_and_source_preserved(self):
        student = fixture(); original = copy.deepcopy(student)
        rows = question_summary(student)
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]['points'], Decimal('.625'))
        self.assertEqual(rows[0]['maximum'], Decimal('1.25'))
        self.assertEqual(rows[0]['erreurs'], ['Erreur de signe.', 'Équivalences manquantes.'])
        self.assertEqual(student, original)
        source = render_student(student, {'titre':'Test','classe':'TEST'}, config())
        self.assertNotIn('Critère machine', source)
        self.assertIn(r'\fcolorbox{SCblue}{white}', source)
        self.assertIn(r'\fontsize{14}{17}', source)
        self.assertNotIn('Bravo', source)
        self.assertEqual(source.count('Q. 1'), 1)
        self.assertIn('0,625/1,25', source)
        self.assertIn(student['corrige_latex'], source)

    def test_exercises_distinct_and_full_credit_has_no_error(self):
        student = fixture()
        student['items'] = [dict(student['items'][0], points_obtenus=.75),
                            dict(student['items'][0], exercice='2')]
        rows = question_summary(student)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['erreurs'], [])
        self.assertEqual(rows[1]['erreurs'], ['Erreur de signe.'])

    def test_detailed_grid_hides_codes_and_rules(self):
        from moteur.render import _GRID_MODE
        student = fixture()
        for item in student['items']:
            item.update(exercice_titre='Équations', question_texte='Résoudre', regle_correction='SECRET_MACHINE')
        token = _GRID_MODE.set('detaillee')
        try:
            source = render_student(student, {'titre':'Test','classe':'TEST'}, config())
        finally:
            _GRID_MODE.reset(token)
        self.assertIn('Équations', source)
        self.assertIn('Résoudre', source)
        self.assertIn('Critère machine', source)
        self.assertNotIn('Q1I0', source)
        self.assertNotIn('SECRET_MACHINE', source)
        self.assertNotIn('Bravo', source)

    def test_layout_mode_persists_and_reaches_exports(self):
        import test_gui
        case = test_gui.GuiWorkflowTests(); case.setUp(); self.addCleanup(case.doCleanups)
        case.pilot()
        from moteur.workflow_v2 import WorkflowApplication
        case.app = WorkflowApplication(case.root/'db.sqlite', case.root/'data', case.root/'legacy')
        layout = case.app.state(case.ident)['layout']
        self.assertEqual(layout['correction']['grid_mode'], 'questions')
        layout['correction']['grid_mode'] = 'detaillee'
        case.app.save_layout(case.ident, layout)
        result = case.app.generate(case.ident, pdf=False)
        tex = next(name for name in result['fichiers'] if name.endswith('.tex') and name != 'notes.tex')
        self.assertIn('Grille détaillée', case.app.file('rendu', result['id'], tex).read_text())
        self.assertEqual(case.app.state(case.ident)['layout']['correction']['grid_mode'], 'detaillee')
        layout['correction']['grid_mode'] = 'invalide'
        with self.assertRaises(ValueError):
            case.app.save_layout(case.ident, layout)

    @unittest.skipUnless(os.environ.get('SMARTCORRECTION_TEST_PDF') == '1', 'real PDF integration')
    def test_six_questions_fit_on_one_a6_panel(self):
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as directory:
            tex = Path(directory)/'questions.tex'
            tex.write_text(render_student(fixture(), {'titre':'Test','classe':'TEST'}, config()))
            pdf = PdfReader(compile_pdf(tex))
            self.assertEqual(len(pdf.pages), 1)
            text = pdf.pages[0].extract_text()
            self.assertEqual(text.count('Erreur de signe.'), 6)
            self.assertNotIn('Critère machine', text)
            self.assertIn('Corrigé', text)
