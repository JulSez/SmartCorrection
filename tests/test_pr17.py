import base64
import io
import json
from pathlib import Path
import tempfile
import unittest

from pypdf import PdfWriter

from moteur.db import database
from moteur.notes import config_from_mapping
from moteur.pr17_patch import compact_corrige_source
from moteur.workflow_v2 import WorkflowApplication, _dummy_student


class Pr17Tests(unittest.TestCase):
    def test_corrige_header_is_one_compact_line(self):
        cfg = config_from_mapping({
            'note_individuelle': {'max': 20},
            'note_groupe': {'max': 0, 'mode': 'aucun'},
            'note_finale': {'max': 20, 'arrondi': .5},
            'absences': {'mode': 'exclure'},
        })
        student = _dummy_student('B', r'\[x=2\]')
        source = compact_corrige_source(student, {'titre': 'Interro 1', 'classe': 'TEST'}, cfg)
        corrige = source.split(r'\def\SCpanel{Corrigé}', 1)[1]
        self.assertNotIn(r'\SCtitle{Corrigé}', corrige)
        self.assertIn(r'\section*{Corrigé}', corrige)
        self.assertNotIn('Interro 1', corrige.split('\n', 3)[1])
        self.assertNotIn(r'\textbf{Version :}', corrige.split('\n', 3)[1])
        self.assertNotIn(r'\textbf{Classe :}', corrige.split('\n', 3)[1])

    def test_verified_corriges_json_becomes_preview_draft_without_being_committed(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        app = WorkflowApplication(root/'db.sqlite', root/'data', root/'legacy')
        app.roster('TEST', 'nom;prenom\nAlpha;Alice\n', True)
        ident = app.create('TEST', 'Sujet')['id']
        writer = PdfWriter(); writer.add_blank_page(width=595, height=842)
        raw = io.BytesIO(); writer.write(raw); writer.close()
        encoded = base64.b64encode(raw.getvalue()).decode()
        app.upload(ident, 'sujet', 'sujet.pdf', encoded)
        data = {'dossier': ident, 'revision': 0, 'corriges': [{'version': 'A', 'corrige_latex': r'\[x=1\]'}]}
        text = json.dumps(data, ensure_ascii=False)
        app.exchange(ident, 'corriges', text, False)
        self.assertFalse(app.state(ident)['corriges_valides'])
        with database(app.db_path) as conn:
            draft = conn.execute("SELECT texte FROM ui_brouillon WHERE dossier_id=? AND etape='corriges'", (ident,)).fetchone()
        self.assertEqual(draft['texte'], text)

    def test_firefox_preview_uses_object_and_loads_after_workflow_v2(self):
        root = Path(__file__).resolve().parents[1]
        preview = (root/'moteur'/'web'/'grid-preview.js').read_text(encoding='utf-8')
        index = (root/'moteur'/'web'/'index.html').read_text(encoding='utf-8')
        self.assertIn('type="application/pdf"', preview)
        self.assertIn("stage==='corriges'", preview)
        self.assertLess(index.index('/workflow-v2.js'), index.index('/grid-preview.js'))


if __name__ == '__main__':
    unittest.main()
