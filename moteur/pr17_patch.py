"""PR17 GUI fixes layered on workflow v2 without changing grading semantics."""
from __future__ import annotations

from contextlib import contextmanager
import json

from . import render as render_module
from . import workflow_v2 as workflow_module
from .db import database
from .gui_service import INDIVIDUAL, response_body
from .notes import config_from_mapping
from .validation import parse_json

WorkflowApplication = workflow_module.WorkflowApplication
_BASE_RENDER_STUDENT = render_module.render_student
_BASE_EXCHANGE = WorkflowApplication.exchange
_BASE_GRID_PREVIEW = WorkflowApplication.grid_preview
_BASE_GENERATE = WorkflowApplication.generate


def compact_corrige_source(student, subject, cfg):
    """Keep the correction sheet unchanged and leave only the Corrigé label on the answer panel."""
    source = _BASE_RENDER_STUDENT(student, subject, cfg)
    esc = render_module.latex_escape_plain_text
    old = '\n'.join([
        r'\def\SCpanel{Corrigé}\setcounter{page}{1}',
        r'\SCtitle{Corrigé}',
        r'{\bfseries ' + esc(subject.get('titre') or 'Évaluation') + r'}\par',
        r'\textbf{Version :} ' + esc(student.get('version') or '?') + r'\hfill\textbf{Classe :} ' + esc(subject.get('classe') or '') + r'\par\vspace{2mm}',
    ])
    new = '\n'.join([
        r'\def\SCpanel{Corrigé}\setcounter{page}{1}',
        r'{\bfseries\color{SCblue} Corrigé}\par\vspace{2mm}',
    ])
    if old not in source:
        raise RuntimeError('En-tête du corrigé introuvable dans le rendu')
    return source.replace(old, new, 1)


@contextmanager
def _compact_renderer():
    """Patch the renderer only while the serialized GUI operation is running."""
    old_render = render_module.render_student
    old_workflow = workflow_module.render_student
    render_module.render_student = compact_corrige_source
    workflow_module.render_student = compact_corrige_source
    try:
        yield
    finally:
        render_module.render_student = old_render
        workflow_module.render_student = old_workflow


def _exchange(self, ident, stage, text, commit=False):
    result = _BASE_EXCHANGE(self, ident, stage, text, commit)
    # A successful verification becomes the source of the visual preview. This is
    # only a draft: the validated educational data is still written on commit.
    if stage == 'corriges' and not commit:
        with database(self.db_path) as conn:
            self._dossier(conn, ident)
            conn.execute('''INSERT INTO ui_brouillon(dossier_id,etape,texte) VALUES(?,?,?)
                ON CONFLICT(dossier_id,etape) DO UPDATE SET texte=excluded.texte''',
                         (ident, stage, text))
    return result


def _corrige_preview(self, ident):
    """Preview the just-verified JSON, falling back to the last committed corrections."""
    with database(self.db_path) as conn:
        dossier = self._dossier(conn, ident)
        draft = conn.execute("SELECT texte FROM ui_brouillon WHERE dossier_id=? AND etape='corriges'", (ident,)).fetchone()
        if draft:
            data = parse_json(response_body(draft['texte'], 'json'))
            corriges = workflow_module._validate_corriges(data, dossier, self._envelope)
        else:
            corriges = workflow_module._saved_corriges(conn, ident)
        if not corriges:
            raise ValueError('Vérifier les corrigés avant de les afficher')
        formats = workflow_module._formats(conn, ident)
        cfg = config_from_mapping(INDIVIDUAL)
        subject = {'titre': dossier['titre'], 'classe': dossier['classe']}
        entries = [(c['version'], c['corrige_latex'], []) for c in corriges]
    with _compact_renderer():
        return workflow_module._compile_preview(subject, cfg, entries, formats, only='corrige')


def _grid_preview(self, ident):
    with _compact_renderer():
        return _BASE_GRID_PREVIEW(self, ident)


def _generate(self, ident, final=False, pdf=True):
    with _compact_renderer():
        return _BASE_GENERATE(self, ident, final=final, pdf=pdf)


WorkflowApplication.exchange = _exchange
WorkflowApplication.corrige_preview = _corrige_preview
WorkflowApplication.grid_preview = _grid_preview
WorkflowApplication.generate = _generate
