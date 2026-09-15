"""PR20: fold copy preprocessing into step 1 and keep it usable without uploaded PDFs."""
from __future__ import annotations

import json
import re

from .db import database
from .gui_service import response_body
from .validation import array, integer, object_fields, parse_json, string
from . import pr18_compat as previous

WorkflowApplication = previous.WorkflowApplication
_BASE_STATE = WorkflowApplication.state
_BASE_DRAFT = WorkflowApplication.draft
_BASE_EXCHANGE = WorkflowApplication.exchange
_BASE_GRID = WorkflowApplication._grid


def _meta_key(ident):
    return f'workflow-pretraitement:{ident}'


def _validate_preprocessing(data, dossier):
    keys = {'dossier', 'revision', 'copies', 'pages_ignorees', 'absents'}
    object_fields(data, keys, {'dossier', 'revision', 'copies', 'pages_ignorees'})
    if data['dossier'] != dossier['id'] or type(data['revision']) is not int or data['revision'] != dossier['revision']:
        raise ValueError('Cette réponse vise un autre dossier ou une ancienne grille. Recopier la consigne actuelle.')
    refs, pages = set(), set()
    clean_copies = []
    for item in array(data['copies'], 'copies', True):
        object_fields(item, {'reference', 'numero', 'version', 'pages'}, {'reference', 'numero', 'version', 'pages'})
        ref = string(item['reference'], 'reference').strip()
        if not re.fullmatch(r'C\d{3,6}', ref) or ref in refs:
            raise ValueError('Référence de copie répétée ou invalide : utiliser C001, C002…')
        refs.add(ref)
        if item['numero'] is not None:
            raise ValueError('Le prétraitement initial ne doit contenir aucun numéro d’élève : utiliser null')
        version = string(item['version'], 'version').strip()
        item_pages = array(item['pages'], 'pages', True)
        checked = []
        for page in item_pages:
            page = integer(page, 'page')
            if page < 1 or page in pages:
                raise ValueError(f'Page {page} invalide ou attribuée deux fois')
            pages.add(page); checked.append(page)
        if checked != sorted(checked):
            raise ValueError('Indiquer les pages dans l’ordre du paquet')
        clean_copies.append({'reference': ref, 'numero': None, 'version': version, 'pages': checked})
    ignored = []
    for item in array(data['pages_ignorees'], 'pages_ignorees'):
        object_fields(item, {'page', 'motif'}, {'page', 'motif'})
        page = integer(item['page'], 'page ignorée')
        if page < 1 or page in pages:
            raise ValueError('Page ignorée déjà affectée ou invalide')
        pages.add(page)
        ignored.append({'page': page, 'motif': string(item['motif'], 'motif')})
    absents = array(data.get('absents', []), 'absents')
    if absents:
        raise ValueError('Les absences ne sont pas déduites par l’IA à cette étape : laisser absents vide')
    return {'dossier': dossier['id'], 'revision': dossier['revision'], 'copies': clean_copies,
            'pages_ignorees': ignored, 'absents': []}


def _read_preprocessing(conn, ident):
    row = conn.execute('SELECT valeur FROM ui_meta WHERE cle=?', (_meta_key(ident),)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def _state(self, ident):
    result = _BASE_STATE(self, ident)
    with database(self.db_path) as conn:
        result['pretraitement'] = _read_preprocessing(conn, ident)
    return result


def _draft(self, ident, stage, text):
    if stage != 'pretraitement':
        return _BASE_DRAFT(self, ident, stage, text)
    if not isinstance(text, str):
        raise ValueError('Texte attendu')
    with database(self.db_path) as conn:
        self._dossier(conn, ident)
        conn.execute('INSERT INTO ui_brouillon VALUES(?,?,?) ON CONFLICT(dossier_id,etape) DO UPDATE SET texte=excluded.texte',
                     (ident, stage, text))
    return {'enregistre': True}


def _exchange(self, ident, stage, text, commit=False):
    if stage != 'pretraitement':
        return _BASE_EXCHANGE(self, ident, stage, text, commit)
    data = parse_json(response_body(text, 'json'))
    with database(self.db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        dossier = self._dossier(conn, ident)
        clean = _validate_preprocessing(data, dossier)
        result = {'copies': len(clean['copies']), 'pages_ignorees': len(clean['pages_ignorees'])}
        if commit:
            conn.execute('INSERT INTO ui_meta(cle,valeur) VALUES(?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur',
                         (_meta_key(ident), json.dumps(clean, ensure_ascii=False)))
            conn.execute('DELETE FROM ui_brouillon WHERE dossier_id=? AND etape=?', (ident, stage))
        else:
            conn.rollback()
        return result


def _materialize_preprocessing(conn, dossier, data):
    if not data or conn.execute('SELECT 1 FROM ui_copie WHERE dossier_id=? LIMIT 1', (dossier['id'],)).fetchone():
        return
    versions = {r['version']: r['id'] for r in conn.execute('SELECT id,version FROM version WHERE sujet_id=?', (dossier['sujet_id'],))}
    for item in data['copies']:
        if item['version'] not in versions:
            raise ValueError(f"Version inconnue dans le prétraitement : {item['version']}")
        cid = conn.execute('INSERT INTO copie(eleve_id,sujet_id,version_id,pdf_path,statut) VALUES(NULL,?,?,?,?)',
                           (dossier['sujet_id'], versions[item['version']], '', 'present')).lastrowid
        conn.execute('INSERT INTO ui_copie(dossier_id,reference,copie_id) VALUES(?,?,?)',
                     (dossier['id'], item['reference'], cid))
        for order, page in enumerate(item['pages'], 1):
            conn.execute('INSERT INTO copie_page VALUES(?,?,?)', (cid, page, order))
    conn.execute('DELETE FROM ui_page_ignoree WHERE dossier_id=?', (dossier['id'],))
    for item in data['pages_ignorees']:
        conn.execute('INSERT INTO ui_page_ignoree VALUES(?,?,?)', (dossier['id'], item['page'], item['motif']))


def _grid(self, conn, dossier, data):
    result = _BASE_GRID(self, conn, dossier, data)
    updated = self._dossier(conn, dossier['id'])
    prep = _read_preprocessing(conn, dossier['id'])
    if prep:
        _materialize_preprocessing(conn, updated, prep)
    return result


WorkflowApplication.state = _state
WorkflowApplication.draft = _draft
WorkflowApplication.exchange = _exchange
WorkflowApplication._grid = _grid
