import tempfile
import unittest
from pathlib import Path

from moteur.db import database
from moteur.import_classe import import_classe_csv
from moteur.import_evaluation import import_evaluation


class ImportClasseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'classe.sqlite'

    def write_csv(self, text, name='classe.csv'):
        path = self.root / name
        path.write_text(text, encoding='utf-8-sig')
        return path

    def test_import_semicolon_csv_assigns_numbers_in_file_order(self):
        path = self.write_csv('Nom;Prénom\nDUPONT;Alice\nMARTIN;Léo\n')
        result = import_classe_csv(path, '1GSpé', self.db)
        self.assertEqual(result['importes'], 2)
        self.assertEqual(result['deja_presents'], 0)
        self.assertEqual(
            result['eleves'],
            [
                {'numero': 1, 'nom': 'DUPONT', 'prenom': 'Alice'},
                {'numero': 2, 'nom': 'MARTIN', 'prenom': 'Léo'},
            ],
        )
        again = import_classe_csv(path, '1GSpé', self.db)
        self.assertEqual(again['importes'], 0)
        self.assertEqual(again['deja_presents'], 2)

    def test_explicit_numbers_and_conflict_are_atomic(self):
        first = self.write_csv('numero,nom,prenom\n7,DUPONT,Alice\n')
        import_classe_csv(first, '1GSpé', self.db)
        conflicting = self.write_csv('numero,nom,prenom\n7,MARTIN,Alice\n8,ROBERT,Emma\n', 'conflit.csv')
        with self.assertRaisesRegex(ValueError, 'Conflit'):
            import_classe_csv(conflicting, '1GSpé', self.db)
        with database(self.db) as conn:
            rows = [dict(r) for r in conn.execute(
                'SELECT numero,nom,prenom FROM eleve WHERE classe=? ORDER BY numero', ('1GSpé',)
            )]
        self.assertEqual(rows, [{'numero': 7, 'nom': 'DUPONT', 'prenom': 'Alice'}])

    def test_evaluation_can_reuse_preimported_roster(self):
        path = self.write_csv('nom,prenom\nDUPONT,Alice\n')
        import_classe_csv(path, '1GSpé', self.db)
        evaluation = {
            'cle': 'reuse-roster',
            'sujet': {'classe': '1GSpé'},
            'versions': [{'version': 'A', 'str_latex': 'Sujet A'}],
            'grille': {
                'validee': True,
                'exercices': [{
                    'numero': '1',
                    'questions': [{
                        'numero': '1',
                        'items': [{'code': 'Q1', 'description': 'Réponse', 'bareme_max': 1}],
                    }],
                }],
            },
            'copies': [{'numero': 1, 'version': 'A', 'pdf_path': 'copie.pdf'}],
        }
        with database(self.db) as conn:
            subject_id = import_evaluation(evaluation, conn, self.root)
            copy = conn.execute('''SELECT e.numero,c.sujet_id FROM copie c
                JOIN eleve e ON e.id=c.eleve_id WHERE c.sujet_id=?''', (subject_id,)).fetchone()
        self.assertEqual(copy['numero'], 1)
        self.assertEqual(copy['sujet_id'], subject_id)


if __name__ == '__main__':
    unittest.main()
