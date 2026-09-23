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
