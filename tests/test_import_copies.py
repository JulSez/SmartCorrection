import json
from pathlib import Path
import tempfile
import unittest

from moteur.db import database, init_db
from moteur.import_classe import import_classe_csv
from moteur.import_copies import import_copies_csv, parse_pages
from moteur.import_evaluation import import_evaluation
from moteur.pipeline import ai_packet


EVALUATION = {
    'cle': 'shared-pdf-test',
    'sujet': {'classe': '1G TEST', 'titre': 'Test PDF partagé'},
    'versions': [
        {'version': 'A', 'str_latex': 'Version A', 'corrige_latex': 'Corrigé A'},
        {'version': 'B', 'str_latex': 'Version B', 'corrige_latex': 'Corrigé B'},
    ],
    'grille': {
        'nom': 'Commune',
        'validee': True,
        'total_points': 1,
        'exercices': [{
            'numero': '1',
            'questions': [{
                'numero': '1',
                'items': [{'code': 'I1', 'description': 'Réponse', 'bareme_max': 1}],
            }],
        }],
    },
}


class SharedPdfCopyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'data.sqlite'
        init_db(self.db)

        roster = self.root / 'classe.csv'
        roster.write_text('numero;nom;prenom\n1;Alpha;Alice\n2;Beta;Bob\n3;Gamma;Chloe\n', encoding='utf-8')
        import_classe_csv(roster, '1G TEST', self.db)
        with database(self.db) as conn:
            self.sid = import_evaluation(EVALUATION, conn, self.root)

        self.pdf = self.root / 'lot.pdf'
        self.pdf.write_bytes(b'%PDF-1.4\n% fake test file\n')

    def test_import_shared_pdf_and_prepare_ai(self):
        mapping = self.root / 'copies.csv'
        mapping.write_text(
            'numero;version;pages;statut\n'
            '1;A;1-2;present\n'
            '2;B;3;present\n'
            '3;A;;absent\n',
            encoding='utf-8',
        )
        result = import_copies_csv(mapping, self.sid, self.pdf, self.db)
        self.assertEqual(result['copies_importees'], 3)
        self.assertEqual(result['pages_assignees'], 3)
        self.assertEqual(result['absents'], 1)

        with database(self.db) as conn:
            rows = conn.execute('SELECT * FROM copie ORDER BY eleve_id').fetchall()
            self.assertEqual(rows[0]['pdf_path'], str(self.pdf.resolve()))
            self.assertEqual(rows[1]['pdf_path'], str(self.pdf.resolve()))
            self.assertEqual(rows[2]['pdf_path'], '')
            pages = [r['page'] for r in conn.execute(
                'SELECT page FROM copie_page WHERE copie_id=? ORDER BY ordre', (rows[0]['id'],)
            )]
            self.assertEqual(pages, [1, 2])
            packet = ai_packet(conn, rows[0]['id'])
            self.assertEqual(packet['source']['pages'], [1, 2])
            self.assertEqual(packet['source']['pdf_path'], str(self.pdf.resolve()))
            self.assertIn('PDF partagé', packet['consigne'])

        repeat = import_copies_csv(mapping, self.sid, self.pdf, self.db)
        self.assertEqual(repeat['deja_presentes'], 3)
        self.assertEqual(repeat['copies_importees'], 0)

    def test_same_source_page_cannot_belong_to_two_copies(self):
        mapping = self.root / 'bad.csv'
        mapping.write_text(
            'numero;version;pages\n1;A;1\n2;B;1\n',
            encoding='utf-8',
        )
        with self.assertRaises(Exception):
            import_copies_csv(mapping, self.sid, self.pdf, self.db)
        with database(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM copie').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM copie_page').fetchone()[0], 0)

    def test_pages_parser(self):
        self.assertEqual(parse_pages('1, 3-5 8'), [1, 3, 4, 5, 8])
        for value in ('0', '4-2', '1,1', '3,2'):
            with self.assertRaises(ValueError):
                parse_pages(value)


if __name__ == '__main__':
    unittest.main()
