"""Workflow v2: formats, batch reference corrections and layout-aware previews/exports."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import uuid

from .calcul import calculate_selection
from .db import database
from .gui_groups import copy_groups
from .gui_service import Application as LegacyApplication, INDIVIDUAL, response_body
from .import_evaluation import import_evaluation
from .notes import config_from_mapping
from .render import compile_pdf, export_results, render_student
from .validation import array, object_fields, parse_json, string

FORMATS = ('A6', 'A5', 'A4')
FORMAT_MM = {'A6': (105.0, 148.0), 'A5': (148.0, 210.0), 'A4': (210.0, 297.0)}


class _BlankScore:
    def __format__(self, _spec):
        return ''


_BLANK = _BlankScore()


def _format_value(value):
    value = str(value or 'A6').upper()
    if value not in FORMATS:
        raise ValueError('Format attendu : A6, A5 ou A4')
    return value


def format_description(value):
    value = _format_value(value)
    width, height = FORMAT_MM[value]
    return f'{value} portrait ({int(width)} × {int(height)} mm)'


def _format_key(ident, part):
    return f'workflow-format:{ident}:{part}'


def _formats(conn, ident):
    result = {}
    for part in ('correction', 'corrige'):
        row = conn.execute('SELECT valeur FROM ui_meta WHERE cle=?', (_format_key(ident, part),)).fetchone()
        result[part] = _format_value(row[0] if row else 'A6')
    return result


def _saved_corriges(conn, ident):
    row = conn.execute("SELECT texte FROM ui_echange WHERE dossier_id=? AND etape='corriges' ORDER BY id DESC LIMIT 1", (ident,)).fetchone()
    if not row:
        return []
    try:
        data = json.loads(row['texte'])
        return data.get('corriges', []) if isinstance(data, dict) else []
    except (ValueError, TypeError):
        return []


def _validate_corriges(data, dossier, envelope):
    envelope(data, dossier, {'corriges'}, {'corriges'})
    result, seen = [], set()
    for item in array(data['corriges'], 'corriges', True):
        object_fields(item, {'version', 'sujet_latex', 'corrige_latex'}, {'version', 'corrige_latex'})
        version = string(item['version'], 'version').strip()
        if version in seen:
            raise ValueError(f'Version répétée : {version}')
        seen.add(version)
        latex = string(item['corrige_latex'], f'corrigé {version}')
        if any(word in latex for word in (r'\documentclass', r'\begin{document}', r'\end{document}')):
            raise ValueError(f'Corrigé {version} : fournir uniquement le corps LaTeX')
        sujet = item.get('sujet_latex') or r'\textit{Sujet joint en PDF.}'
        if not isinstance(sujet, str):
            raise ValueError('sujet_latex doit être une chaîne')
        result.append({'version': version, 'sujet_latex': sujet, 'corrige_latex': latex})
    return result


def _apply_corriges(conn, dossier, corriges):
    """Update reference corrections after a grid exists; version identity stays fixed."""
    if not dossier['sujet_id']:
        return
    versions = {r['version']: r['id'] for r in conn.execute('SELECT id,version FROM version WHERE sujet_id=?', (dossier['sujet_id'],))}
    if set(versions) != {c['version'] for c in corriges}:
        raise ValueError('Les versions du corrigé ont changé : revenir à la grille pour créer une nouvelle révision')
    changed = []
    for item in corriges:
        vid = versions[item['version']]
        old = conn.execute('SELECT str_latex FROM corrige WHERE version_id=?', (vid,)).fetchone()
        conn.execute('INSERT INTO corrige(version_id,str_latex) VALUES(?,?) ON CONFLICT(version_id) DO UPDATE SET str_latex=excluded.str_latex',
                     (vid, item['corrige_latex']))
        if old and old[0] != item['corrige_latex']:
            changed.append(vid)
    if changed:
        marks = ','.join('?' for _ in changed)
        conn.execute(f'''UPDATE ui_copie SET a_revoir='Corrigé de référence modifié : vérifier cette correction'
            WHERE dossier_id=? AND copie_id IN (
              SELECT co.copie_id FROM correction co JOIN copie c ON c.id=co.copie_id
              WHERE c.version_id IN ({marks})
            )''', (dossier['id'], *changed))
        conn.execute('UPDATE ui_dossier SET echantillon_valide=0,termine=0 WHERE id=?', (dossier['id'],))
        conn.execute('UPDATE ui_rendu SET valide=0 WHERE dossier_id=?', (dossier['id'],))


def _dummy_student(version, corrige_latex, items=None):
    return {
        'numero': None,
        'label': '........................................................',
        'version': version or 'Commune',
        'statut': 'present',
        'note_individuelle': _BLANK,
        'note_groupe': 0,
        'note_finale': _BLANK,
        'camarades': [],
        'items': [dict(item, points_obtenus=_BLANK, commentaire=None, annotation=None) for item in (items or [])],
        'annotations': [],
        'conseils': [],
        'commentaire_global': None,
        'corrige_latex': corrige_latex,
    }


def _target_points(fmt):
    width, height = FORMAT_MM[_format_value(fmt)]
    return width * 72 / 25.4, height * 72 / 25.4


def _layout_pair_pages(reader, correction_fmt, corrige_fmt, *, only=None):
    """Convert legacy A6+A6 landscape sheets to independently sized portrait streams."""
    from pypdf import PdfWriter, Transformation

    correction_fmt = _format_value(correction_fmt)
    corrige_fmt = _format_value(corrige_fmt)
    if only is None and correction_fmt == corrige_fmt == 'A6':
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        return writer

    left_pages, right_pages = [], []
    for page in reader.pages:
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        half = width / 2
        left_pages.append((page, 0.0, half, height))
        right_pages.append((page, half, half, height))

    writer = PdfWriter()

    def add_side(page, source_x, source_w, source_h, fmt):
        target_w, target_h = _target_points(fmt)
        scale = min(target_w / source_w, target_h / source_h)
        x = (target_w - source_w * scale) / 2 - source_x * scale
        y = (target_h - source_h * scale) / 2
        sheet = writer.add_blank_page(width=target_w, height=target_h)
        sheet.merge_transformed_page(page, Transformation().scale(scale).translate(tx=x, ty=y))

    if only in (None, 'correction'):
        for page, source_x, source_w, source_h in left_pages:
            add_side(page, source_x, source_w, source_h, correction_fmt)
    if only in (None, 'corrige'):
        for page, source_x, source_w, source_h in right_pages:
            add_side(page, source_x, source_w, source_h, corrige_fmt)
    return writer


def reformat_pair_pdf(path, correction_fmt, corrige_fmt, *, only=None):
    from pypdf import PdfReader

    raw = Path(path).read_bytes()
    reader = PdfReader(io.BytesIO(raw))
    writer = _layout_pair_pages(reader, correction_fmt, corrige_fmt, only=only)
    try:
        output = io.BytesIO()
        writer.write(output)
        data = output.getvalue()
    finally:
        writer.close()
    if only is None:
        Path(path).write_bytes(data)
    return data


def _compile_preview(subject, cfg, entries, formats, *, only=None):
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    try:
        with tempfile.TemporaryDirectory(prefix='.workflow-preview-') as tmp:
            folder = Path(tmp)
            for index, (version, corrige, items) in enumerate(entries, 1):
                source = render_student(_dummy_student(version, corrige, items), subject, cfg)
                source = source.replace('Aucun conseil enregistré.', r'\vspace{10mm}')
                tex = folder / f'preview_{index}.tex'
                tex.write_text(source, encoding='utf-8')
                pair = compile_pdf(tex)
                data = reformat_pair_pdf(pair, formats['correction'], formats['corrige'], only=only)
                reader = PdfReader(io.BytesIO(data))
                for page in reader.pages:
                    writer.add_page(page)
            output = io.BytesIO()
            writer.write(output)
            data = output.getvalue()
    finally:
        writer.close()
    if not PdfReader(io.BytesIO(data)).pages:
        raise RuntimeError('Aucune page produite pour l’aperçu')
    return data


def _refresh_manifest(folder, sujet_id, pdf):
    folder = Path(folder)
    files = {}
    for path in sorted(folder.iterdir()):
        if path.name == 'manifest.json' or path.name.endswith('.a6.pdf'):
            continue
        if path.suffix in {'.json', '.csv', '.tex', '.pdf', '.md'}:
            files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (folder / 'manifest.json').write_text(json.dumps({'format_version': 1, 'sujet_id': sujet_id, 'pdf': pdf, 'files': files}, indent=2) + '\n', encoding='utf-8')


class WorkflowApplication(LegacyApplication):
    """Seven-step GUI workflow while keeping the grading engine backwards compatible."""

    def state(self, ident):
        result = super().state(ident)
        with database(self.db_path) as conn:
            result['formats'] = _formats(conn, ident)
            result['corriges'] = _saved_corriges(conn, ident)
            result['corriges_valides'] = bool(result['corriges'])
        return result

    def save_formats(self, ident, correction, corrige):
        correction, corrige = _format_value(correction), _format_value(corrige)
        with database(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            self._dossier(conn, ident)
            for part, value in (('correction', correction), ('corrige', corrige)):
                conn.execute('INSERT INTO ui_meta(cle,valeur) VALUES(?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur',
                             (_format_key(ident, part), value))
            conn.execute('UPDATE ui_rendu SET valide=0 WHERE dossier_id=?', (ident,))
        return {'correction': correction, 'corrige': corrige}

    def draft(self, ident, stage, text):
        if stage != 'corriges':
            return super().draft(ident, stage, text)
        if not isinstance(text, str):
            raise ValueError('Texte attendu')
        with database(self.db_path) as conn:
            self._dossier(conn, ident)
            conn.execute('INSERT INTO ui_brouillon VALUES(?,?,?) ON CONFLICT(dossier_id,etape) DO UPDATE SET texte=excluded.texte',
                         (ident, stage, text))
        return {'enregistre': True}

    def exchange(self, ident, stage, text, commit=False):
        if stage != 'corriges':
            return super().exchange(ident, stage, text, commit)
        data = parse_json(response_body(text, 'json'))
        with database(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            dossier = self._dossier(conn, ident)
            corriges = _validate_corriges(data, dossier, self._envelope)
            result = {'corriges': [{'version': c['version'], 'caracteres': len(c['corrige_latex'])} for c in corriges]}
            if commit:
                self._record(conn, dossier, stage, data)
                _apply_corriges(conn, dossier, corriges)
        return result

    def _grid(self, conn, dossier, data):
        self._envelope(data, dossier, {'versions', 'grilles'}, {'grilles'})
        corriges = _saved_corriges(conn, dossier['id'])
        if not corriges:
            raise ValueError('Valider d’abord tous les corrigés de référence')
        validated = _validate_corriges({'dossier': dossier['id'], 'revision': dossier['revision'], 'corriges': corriges}, dossier, self._envelope)
        version_names = [c['version'] for c in validated]
        if 'versions' in data:
            supplied = []
            for item in array(data['versions'], 'versions', True):
                object_fields(item, {'version', 'sujet_latex'}, {'version'})
                supplied.append(string(item['version']))
            if supplied != version_names:
                raise ValueError('La grille doit reprendre exactement les versions déjà validées dans les corrigés')
        versions = [{'version': c['version'], 'str_latex': c['sujet_latex']} for c in validated]
        grids = array(data['grilles'], 'grilles', True)
        for grid in grids:
            if not isinstance(grid, dict) or 'validee' in grid:
                raise ValueError('La validation de la grille appartient à l’enseignant dans l’application')
        evaluation = {
            'cle': f"interface-{dossier['id']}-{dossier['revision']+1}",
            'sujet': {'classe': dossier['classe'], 'titre': dossier['titre'], 'config_notes': INDIVIDUAL},
            'versions': versions,
            'grilles': [dict(g, validee=True) for g in grids],
        }
        sid = import_evaluation(evaluation, conn)
        copy_groups(conn, dossier['sujet_id'], sid)
        version_ids = {r['version']: r['id'] for r in conn.execute('SELECT id,version FROM version WHERE sujet_id=?', (sid,))}
        for item in validated:
            conn.execute('INSERT INTO corrige(version_id,str_latex) VALUES(?,?)', (version_ids[item['version']], item['corrige_latex']))
        copies = self._copies(conn, dossier)
        for copy in copies:
            if copy['version'] not in version_ids:
                raise ValueError(f"La copie {copy['reference']} utilise encore la version {copy['version']}")
            cid = conn.execute('INSERT INTO copie(eleve_id,sujet_id,version_id,pdf_path,statut) VALUES(?,?,?,?,?)',
                               (copy['eleve_id'], sid, version_ids[copy['version']], copy['pdf_path'], copy['statut'])).lastrowid
            for order, page in enumerate(copy['pages'], 1):
                conn.execute('INSERT INTO copie_page VALUES(?,?,?)', (cid, page, order))
            conn.execute('UPDATE ui_copie SET copie_id=?,a_revoir=NULL WHERE dossier_id=? AND reference=?',
                         (cid, dossier['id'], copy['reference']))
        conn.execute('UPDATE ui_dossier SET sujet_id=?,revision=revision+1,echantillon_valide=0,termine=0 WHERE id=?', (sid, dossier['id']))
        conn.execute('INSERT INTO ui_revision VALUES(?,?,?)', (dossier['id'], dossier['revision'] + 1, sid))
        return {
            'grilles': [dict(r) for r in conn.execute('SELECT id,nom,total_points FROM grille WHERE sujet_id=?', (sid,))],
            'copies_a_reprendre': len([c for c in copies if c['correction_id']]),
            'revision': dossier['revision'] + 1,
        }

    def corrige_preview(self, ident):
        with database(self.db_path) as conn:
            dossier = self._dossier(conn, ident)
            corriges = _saved_corriges(conn, ident)
            if not corriges:
                raise ValueError('Valider les corrigés avant de les afficher')
            formats = _formats(conn, ident)
            cfg = config_from_mapping(INDIVIDUAL)
            subject = {'titre': dossier['titre'], 'classe': dossier['classe']}
            entries = [(c['version'], c['corrige_latex'], []) for c in corriges]
        return _compile_preview(subject, cfg, entries, formats, only='corrige')

    def grid_preview(self, ident):
        with database(self.db_path) as conn:
            dossier = self._dossier(conn, ident)
            if not dossier['sujet_id']:
                raise ValueError('Enregistrer la grille avant de générer son aperçu')
            subject = dict(conn.execute('SELECT * FROM sujet WHERE id=?', (dossier['sujet_id'],)).fetchone())
            cfg = config_from_mapping(json.loads(subject['config_notes'] or '{}'))
            formats = _formats(conn, ident)
            entries = []
            for grid in conn.execute('''SELECT g.id,g.version_id,v.version,co.str_latex FROM grille g
                LEFT JOIN version v ON v.id=g.version_id
                LEFT JOIN corrige co ON co.version_id=COALESCE(g.version_id,(SELECT id FROM version WHERE sujet_id=g.sujet_id ORDER BY id LIMIT 1))
                WHERE g.sujet_id=? ORDER BY g.id''', (dossier['sujet_id'],)):
                items = [dict(row) for row in conn.execute('''SELECT e.numero exercice,q.numero question,i.description,i.bareme_max
                    FROM item i JOIN question q ON q.id=i.question_id JOIN exercice e ON e.id=q.exercice_id
                    WHERE i.grille_id=? ORDER BY e.ordre,q.ordre,i.ordre,i.id''', (grid['id'],))]
                corrige = grid['str_latex'] or r'\textit{Aucun corrigé enregistré pour cette version.}'
                entries.append((grid['version'] or 'Commune', corrige, items))
        return _compile_preview(subject, cfg, entries, formats)

    def generate(self, ident, final=False, pdf=True):
        folder = None
        try:
            with database(self.db_path) as conn:
                dossier = self._dossier(conn, ident)
                copies = self._copies(conn, dossier)
                if final and not dossier['echantillon_valide']:
                    raise ValueError('Valider l’échantillon avant le document final')
                selected = [c for c in copies if not c['exclue_final']] if final else [c for c in copies if c['echantillon']]
                if not selected:
                    raise ValueError('Inclure au moins une copie dans le document final' if final else 'Sélectionner des copies à afficher')
                for copy in selected:
                    if copy['a_revoir']:
                        raise ValueError(f"{copy['reference']} reste à revoir : {copy['a_revoir']}")
                result = calculate_selection(conn, dossier['sujet_id'], [c['copie_id'] for c in selected], allow_groups=True)
                if final:
                    result['copies_exclues'] = [c['reference'] for c in copies if c['exclue_final']]
                labels = {c['copie_id']: c['reference'] for c in selected}
                for row in result['notes']:
                    if row['numero'] is None:
                        row['label'] = f"{labels[row['copie_id']]} - élève non identifié"
                formats = _formats(conn, ident)
                rid = uuid.uuid4().hex
                folder = self.data_dir / 'rendus' / rid
                export_results(conn, result, folder, pdf=pdf, combined=False)
                if pdf:
                    student_pdfs = sorted([*folder.glob('eleve_*.pdf'), *folder.glob('copie_*.pdf')])
                    for path in student_pdfs:
                        reformat_pair_pdf(path, formats['correction'], formats['corrige'])
                    from pypdf import PdfWriter
                    writer = PdfWriter()
                    try:
                        for path in student_pdfs:
                            writer.append(str(path))
                        writer.write(str(folder / 'corrections.pdf'))
                    finally:
                        writer.close()
                    _refresh_manifest(folder, result['sujet']['id'], True)
                conn.execute('INSERT INTO ui_rendu(id,dossier_id,revision,final,chemin) VALUES(?,?,?,?,?)',
                             (rid, ident, dossier['revision'], int(final), str(folder)))
                if final:
                    conn.execute('UPDATE ui_dossier SET termine=1 WHERE id=?', (ident,))
            return {'id': rid, 'pdf': pdf, 'fichiers': sorted(p.name for p in folder.iterdir())}
        except Exception:
            if folder and folder.exists():
                shutil.rmtree(folder, ignore_errors=True)
            raise
