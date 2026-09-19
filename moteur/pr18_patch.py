"""PR18: richer document layout choices and progressive previews."""
from __future__ import annotations

import json
from contextlib import contextmanager

from . import workflow_v2 as workflow
from . import render as render_module
from .db import database
from .gui_service import INDIVIDUAL, response_body
from .notes import config_from_mapping
from .validation import parse_json

WorkflowApplication = workflow.WorkflowApplication
_BASE_STATE = WorkflowApplication.state
_BASE_SAVE_FORMATS = WorkflowApplication.save_formats
_BASE_GENERATE = WorkflowApplication.generate

SIZES = ('A6', 'A5', 'A4')
ORIENTATIONS = ('portrait', 'paysage')
ASSEMBLIES = ('separe', 'cote-a-cote')
PRINT_FORMATS = ('auto', 'A6', 'A5', 'A4')
LOREM = (r'\section*{Exemple} Lorem ipsum dolor sit amet, consectetur adipiscing elit. '
         r'\[x^2=5\iff x=\pm\sqrt5\]')

_DEFAULT_LAYOUT = {
    'correction': {'size': 'A6', 'orientation': 'portrait', 'pages': 1, 'newpage_after_correction': True},
    'corrige': {'size': 'A6', 'orientation': 'portrait', 'pages': 1, 'columns': 1},
    'assembly': 'cote-a-cote',
    'print_format': 'auto',
}


def _meta_key(ident, name):
    return f'workflow-layout:{ident}:{name}'


def _read_json(conn, ident, name, default):
    row = conn.execute('SELECT valeur FROM ui_meta WHERE cle=?', (_meta_key(ident, name),)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except Exception:
        return default


def _layout(conn, ident):
    raw = _read_json(conn, ident, 'config', _DEFAULT_LAYOUT)
    out = json.loads(json.dumps(_DEFAULT_LAYOUT))
    if isinstance(raw, dict):
        for part in ('correction', 'corrige'):
            if isinstance(raw.get(part), dict):
                out[part].update(raw[part])
        for key in ('assembly', 'print_format'):
            if key in raw:
                out[key] = raw[key]
    return _validate_layout(out)


def _validate_layout(layout):
    for part in ('correction', 'corrige'):
        item = layout[part]
        if item.get('size') not in SIZES:
            raise ValueError('Taille attendue : A6, A5 ou A4')
        if item.get('orientation') not in ORIENTATIONS:
            raise ValueError('Orientation attendue : portrait ou paysage')
        pages = int(item.get('pages', 1))
        if pages < 1 or pages > 8:
            raise ValueError('Nombre de pages attendu : 1 à 8')
        item['pages'] = pages
    page_break = layout['correction'].get('newpage_after_correction', True)
    if type(page_break) is not bool:
        raise ValueError('Saut de page après correction : booléen attendu')
    layout['correction']['newpage_after_correction'] = page_break
    cols = int(layout['corrige'].get('columns', 1))
    if cols not in (1, 2):
        raise ValueError('Le corrigé accepte 1 ou 2 colonnes')
    layout['corrige']['columns'] = cols
    if layout.get('assembly') not in ASSEMBLIES:
        raise ValueError('Assemblage attendu : séparé ou côte à côte')
    if layout.get('print_format') not in PRINT_FORMATS:
        raise ValueError('Format terminal attendu : auto, A6, A5 ou A4')
    return layout


def _paper_mm(size, orientation):
    w, h = workflow.FORMAT_MM[size]
    return (h, w) if orientation == 'paysage' else (w, h)


def _auto_terminal(layout):
    c = layout['correction']; r = layout['corrige']
    cw, ch = _paper_mm(c['size'], c['orientation'])
    rw, rh = _paper_mm(r['size'], r['orientation'])
    if layout['assembly'] == 'cote-a-cote':
        width, height = cw + rw, max(ch, rh)
    else:
        width, height = max(cw, rw), max(ch, rh)
    for name, w, h in [('A6',105,148),('A5',148,210),('A4',210,297)]:
        if (width <= w and height <= h) or (width <= h and height <= w):
            return name
    return 'A4'


def _layout_summary(layout):
    c, r = layout['correction'], layout['corrige']
    terminal = _auto_terminal(layout) if layout['print_format'] == 'auto' else layout['print_format']
    join = 'côte à côte' if layout['assembly'] == 'cote-a-cote' else 'feuilles séparées'
    extra = ''
    if c['size'] == r['size'] == 'A6' and c['orientation'] == r['orientation'] == 'portrait' and layout['assembly'] == 'cote-a-cote':
        extra = ' Deux A6 portrait côte à côte forment une feuille A5 paysage.'
        if terminal == 'A4':
            extra += ' Deux feuilles A5 paysage seront imposées sur chaque feuille A4.'
    return (f"Correction : {c['pages']}× {c['size']} {c['orientation']} ; "
            f"Corrigé : {r['pages']}× {r['size']} {r['orientation']}, {r['columns']} colonne(s) ; "
            f"assemblage : {join} ; impression terminale : {terminal}." + extra)


def _state(self, ident):
    result = _BASE_STATE(self, ident)
    with database(self.db_path) as conn:
        layout = _layout(conn, ident)
    result['layout'] = layout
    result['layout_summary'] = _layout_summary(layout)
    result['formats'] = {'correction': layout['correction']['size'], 'corrige': layout['corrige']['size']}
    return result


def _save_layout(self, ident, payload):
    layout = json.loads(json.dumps(_DEFAULT_LAYOUT))
    if isinstance(payload, dict):
        for part in ('correction', 'corrige'):
            if isinstance(payload.get(part), dict):
                layout[part].update(payload[part])
        for key in ('assembly', 'print_format'):
            if key in payload:
                layout[key] = payload[key]
    _validate_layout(layout)
    with database(self.db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        self._dossier(conn, ident)
        conn.execute('INSERT INTO ui_meta(cle,valeur) VALUES(?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur',
                     (_meta_key(ident, 'config'), json.dumps(layout, ensure_ascii=False)))
        for part in ('correction', 'corrige'):
            conn.execute('INSERT INTO ui_meta(cle,valeur) VALUES(?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur',
                         (workflow._format_key(ident, part), layout[part]['size']))
        conn.execute('UPDATE ui_rendu SET valide=0 WHERE dossier_id=?', (ident,))
    return {'layout': layout, 'summary': _layout_summary(layout)}


def _save_formats(self, ident, correction='A6', corrige='A6', **kwargs):
    if kwargs.get('layout'):
        return _save_layout(self, ident, kwargs['layout'])
    return _BASE_SAVE_FORMATS(self, ident, correction, corrige)


def _dummy_entries(stage, corriges=None):
    if stage == 'layout':
        return [('A', LOREM, [
            {'exercice': '1', 'question': '1', 'description': 'Critère de démonstration', 'bareme_max': 2},
            {'exercice': '1', 'question': '2', 'description': 'Deuxième critère de démonstration', 'bareme_max': 3},
        ])]
    if stage == 'corriges':
        return [(c['version'], c['corrige_latex'], [
            {'exercice': '1', 'question': '1', 'description': 'La grille sera ajoutée à l’étape suivante', 'bareme_max': 0},
        ]) for c in corriges]
    return []


def _apply_source_layout(source, layout):
    if layout['corrige']['columns'] == 2:
        marker = r'\def\SCpanel{Corrigé}\setcounter{page}{1}'
        source = source.replace(marker, marker + '\n' + r'\setlength{\columnsep}{5mm}\begin{multicols}{2}', 1)
        source = source.replace(r'\end{document}', r'\end{multicols}\end{document}', 1)
        source = source.replace(r'\usepackage{xcolor}', r'\usepackage{xcolor}\usepackage{multicol}', 1)
    return source


@contextmanager
def _layout_renderer(layout):
    base = workflow.render_student
    def render(student, subject, cfg):
        token = render_module._CORRECTION_PAGE_BREAK.set(layout['correction'].get('newpage_after_correction', True))
        try:
            return _apply_source_layout(base(student, subject, cfg), layout)
        finally:
            render_module._CORRECTION_PAGE_BREAK.reset(token)
    old = workflow.render_student
    workflow.render_student = render
    try:
        yield
    finally:
        workflow.render_student = old


def _progressive_preview(self, ident, stage):
    with database(self.db_path) as conn:
        dossier = self._dossier(conn, ident)
        layout = _layout(conn, ident)
        cfg = config_from_mapping(INDIVIDUAL)
        subject = {'titre': dossier['titre'], 'classe': dossier['classe']}
        if stage == 'layout':
            entries = _dummy_entries('layout')
        elif stage == 'corriges':
            draft = conn.execute("SELECT texte FROM ui_brouillon WHERE dossier_id=? AND etape='corriges'", (ident,)).fetchone()
            corriges = []
            if draft:
                data = parse_json(response_body(draft['texte'], 'json'))
                corriges = workflow._validate_corriges(data, dossier, self._envelope)
            if not corriges:
                corriges = workflow._saved_corriges(conn, ident)
            if not corriges:
                raise ValueError('Vérifier les corrigés avant de les afficher')
            entries = _dummy_entries('corriges', corriges)
        else:
            if not dossier['sujet_id']:
                raise ValueError('Enregistrer la grille avant de générer son aperçu')
            entries = []
            for grid in conn.execute('''SELECT g.id,g.version_id,v.version,co.str_latex FROM grille g
                LEFT JOIN version v ON v.id=g.version_id
                LEFT JOIN corrige co ON co.version_id=COALESCE(g.version_id,(SELECT id FROM version WHERE sujet_id=g.sujet_id ORDER BY id LIMIT 1))
                WHERE g.sujet_id=? ORDER BY g.id''', (dossier['sujet_id'],)):
                items = [dict(row) for row in conn.execute('''SELECT e.numero exercice,q.numero question,i.description,i.bareme_max
                    FROM item i JOIN question q ON q.id=i.question_id JOIN exercice e ON e.id=q.exercice_id
                    WHERE i.grille_id=? ORDER BY e.ordre,q.ordre,i.ordre,i.id''', (grid['id'],))]
                entries.append((grid['version'] or 'Commune', grid['str_latex'] or LOREM, items))
    with _layout_renderer(layout):
        return workflow._compile_preview(subject, cfg, entries,
            {'correction': layout['correction']['size'], 'corrige': layout['corrige']['size']},
            only='corrige' if stage == 'corriges' else None)


def _layout_preview(self, ident): return _progressive_preview(self, ident, 'layout')
def _corrige_preview(self, ident): return _progressive_preview(self, ident, 'corriges')
def _grid_preview(self, ident): return _progressive_preview(self, ident, 'grid')

WorkflowApplication.state = _state
WorkflowApplication.save_layout = _save_layout
WorkflowApplication.save_formats = _save_formats
WorkflowApplication.layout_preview = _layout_preview
WorkflowApplication.corrige_preview = _corrige_preview
WorkflowApplication.grid_preview = _grid_preview

def _generate(self, ident, final=False, pdf=True):
    with database(self.db_path) as conn:
        layout = _layout(conn, ident)
    token = render_module._CORRECTION_PAGE_BREAK.set(layout['correction'].get('newpage_after_correction', True))
    try:
        return _BASE_GENERATE(self, ident, final=final, pdf=pdf)
    finally:
        render_module._CORRECTION_PAGE_BREAK.reset(token)

WorkflowApplication.generate = _generate
