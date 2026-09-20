"""Blank correction-sheet preview generated immediately after grid validation."""
from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

from .db import database
from .notes import config_from_mapping
from .render import compile_pdf, render_student


class _BlankScore:
    """Render as an empty score while keeping the normal sheet renderer unchanged."""

    def __format__(self, _spec):
        return ''


_BLANK = _BlankScore()


def blank_sheet_source(subject, cfg, version, items):
    """Build the exact correction layout with question totals and grading fields empty."""
    student = {
        'grille_vierge': True,
        'numero': None,
        'label': '........................................................',
        'version': version or 'Commune',
        'statut': 'present',
        'note_individuelle': _BLANK,
        'note_groupe': 0,
        'note_finale': _BLANK,
        'camarades': [],
        'items': [dict(item, points_obtenus=_BLANK, commentaire=None, annotation=None) for item in items],
        'annotations': [],
        'conseils': [],
        'commentaire_global': None,
        'corrige_latex': r'\textit{Le corrigé sera ajouté à l’étape suivante.}',
    }
    source = render_student(student, subject, cfg)
    # A blank preview should reserve the advice area without pretending that a
    # correction has already been completed.
    return source.replace('Aucun conseil enregistré.', r'\vspace{10mm}')


def build_grid_preview(app, ident):
    """Return one A5 preview per grid/version, combined in a single PDF byte stream."""
    with database(app.db_path) as conn:
        dossier = conn.execute('SELECT * FROM ui_dossier WHERE id=?', (ident,)).fetchone()
        if not dossier:
            raise ValueError('Dossier introuvable')
        if not dossier['sujet_id']:
            raise ValueError('Enregistrer la grille avant de générer son aperçu')
        subject = conn.execute('SELECT * FROM sujet WHERE id=?', (dossier['sujet_id'],)).fetchone()
        cfg = config_from_mapping(json.loads(subject['config_notes'] or '{}'))
        grids = conn.execute('''SELECT g.id,v.version FROM grille g
            LEFT JOIN version v ON v.id=g.version_id
            WHERE g.sujet_id=? ORDER BY g.id''', (dossier['sujet_id'],)).fetchall()
        if not grids:
            raise ValueError('Aucune grille enregistrée')

        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        try:
            with tempfile.TemporaryDirectory(prefix='.grid-preview-', dir=app.data_dir) as tmp:
                folder = Path(tmp)
                for index, grid in enumerate(grids, 1):
                    items = [dict(row) for row in conn.execute('''SELECT e.numero exercice,q.numero question,
                        i.description,i.bareme_max FROM item i
                        JOIN question q ON q.id=i.question_id
                        JOIN exercice e ON e.id=q.exercice_id
                        WHERE i.grille_id=? ORDER BY e.ordre,q.ordre,i.ordre,i.id''', (grid['id'],))]
                    tex = folder/f'grille_{index}.tex'
                    tex.write_text(blank_sheet_source(dict(subject), cfg, grid['version'], items), encoding='utf-8')
                    preview = compile_pdf(tex)
                    writer.append(str(preview))
                output = io.BytesIO()
                writer.write(output)
                raw = output.getvalue()
        finally:
            writer.close()
    # Parse once before returning so a corrupt/incomplete PDF never reaches the browser.
    if not PdfReader(io.BytesIO(raw)).pages:
        raise RuntimeError('Aucune page produite pour l’aperçu de la grille')
    return raw
