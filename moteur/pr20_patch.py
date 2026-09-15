"""PR20: fold copy preprocessing into step 1 and keep it usable without uploaded PDFs."""
from __future__ import annotations

import json
import re

from .db import database
from .gui_service import response_body
from .identites import candidates
from .validation import array, integer, object_fields, parse_json, string
from . import pr18_compat as previous

WorkflowApplication = previous.WorkflowApplication
_BASE_STATE = WorkflowApplication.state
_BASE_DRAFT = WorkflowApplication.draft
_BASE_EXCHANGE = WorkflowApplication.exchange
_BASE_GRID = WorkflowApplication._grid


def _meta_key(ident):
    return f'workflow-pretraitement:{ident}'


def _anonymity_key(ident):
    return f'workflow-anonymat:{ident}'


def _read_anonymity(conn, ident):
    row = conn.execute('SELECT valeur FROM ui_meta WHERE cle=?', (_anonymity_key(ident),)).fetchone()
    return True if not row else row[0] != '0'


def _resolve_pupil(conn, classe, nom, prenom):
    matches = [m for m in candidates(conn, nom, prenom) if classe in m['classes'] and m['score'] == 1]
    if len(matches) == 1:
        return matches[0]['id']
    if not matches:
        raise ValueError(f"Élève introuvable dans la classe : {prenom} {nom}. Corrigez le nom dans le JSON ou réactivez l’anonymat.")
    raise ValueError(f"Identité ambiguë dans la classe : {prenom} {nom}. Corrigez le JSON.")


def _validate_preprocessing(data, dossier, anonymat=True, conn=None):
    keys = {'dossier', 'revision', 'copies', 'pages_ignorees', 'absents'}
    object_fields(data, keys, {'dossier', 'revision', 'copies', 'pages_ignorees'})
    if data['dossier'] != dossier['id'] or type(data['revision']) is not int or data['revision'] != dossier['revision']:
        raise ValueError('Cette réponse vise un autre dossier ou une ancienne grille. Recopier la consigne actuelle.')
    refs, pages, pupils = set(), set(), set()
    clean_copies = []
    for item in array(data['copies'], 'copies', True):
        allowed = {'reference', 'numero', 'version', 'pages', 'nom', 'prenom'}
        required = {'reference', 'numero', 'version', 'pages'} if anonymat else allowed
        object_fields(item, allowed, required)
        ref = string(item['reference'], 'reference').strip()
        if not re.fullmatch(r'C\d{3,6}', ref) or ref in refs:
            raise ValueError('Référence de copie répétée ou invalide : utiliser C001, C002…')
        refs.add(ref)
        if item['numero'] is not None:
            raise ValueError('Le champ numero doit rester null : SmartCorrection gère les identités localement.')
        version = string(item['version'], 'version').strip()
        pupil_id = None
        nom = prenom = None
        if anonymat:
            if item.get('nom') not in (None, '') or item.get('prenom') not in (None, ''):
                raise ValueError('Mode anonymat actif : ne pas inclure nom/prénom dans le JSON.')
        else:
            nom = string(item['nom'], 'nom').strip()
            prenom = string(item['prenom'], 'prenom').strip()
            if conn is None:
                raise ValueError('Connexion requise pour rapprocher les identités')
            pupil_id = _resolve_pupil(conn, dossier['classe'], nom, prenom)
            if pupil_id in pupils:
                raise ValueError(f'Le même élève est associé à plusieurs copies : {prenom} {nom}')
            pupils.add(pupil_id)
        item_pages = array(item['pages'], 'pages', True)
        checked = []
        for page in item_pages:
            page = integer(page, 'page')
            if page < 1 or page in pages:
                raise ValueError(f'Page {page} invalide ou attribuée deux fois')
            pages.add(page); checked.append(page)
        if checked != sorted(checked):
            raise ValueError('Indiquer les pages dans l’ordre du paquet')
        clean = {'reference': ref, 'numero': None, 'version': version, 'pages': checked}
        if not anonymat:
            clean.update({'nom': nom, 'prenom': prenom, 'eleve_id': pupil_id})
        clean_copies.append(clean)
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
            'pages_ignorees': ignored, 'absents': [], 'anonymat': anonymat}


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
        result['anonymat'] = _read_anonymity(conn, ident)
    return result


def _save_anonymity(self, ident, active=True):
    if type(active) is not bool:
        raise ValueError('Mode anonymat invalide')
    with database(self.db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        self._dossier(conn, ident)
        if conn.execute('SELECT 1 FROM ui_copie WHERE dossier_id=? LIMIT 1', (ident,)).fetchone():
            raise ValueError('Le mode anonymat ne peut plus être changé après création des copies. Créez une nouvelle évaluation si nécessaire.')
        current = _read_anonymity(conn, ident)
        conn.execute('INSERT INTO ui_meta(cle,valeur) VALUES(?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur',
                     (_anonymity_key(ident), '1' if active else '0'))
        if current != active:
            conn.execute('DELETE FROM ui_meta WHERE cle=?', (_meta_key(ident),))
            conn.execute("DELETE FROM ui_brouillon WHERE dossier_id=? AND etape='pretraitement'", (ident,))
    return {'anonymat': active, 'pretraitement_invalide': current != active}


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
        anonymat = _read_anonymity(conn, ident)
        clean = _validate_preprocessing(data, dossier, anonymat, conn)
        result = {'copies': len(clean['copies']), 'pages_ignorees': len(clean['pages_ignorees']),
                  'identifiees': sum(1 for c in clean['copies'] if c.get('eleve_id'))}
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
        pupil_id = item.get('eleve_id')
        cid = conn.execute('INSERT INTO copie(eleve_id,sujet_id,version_id,pdf_path,statut) VALUES(?,?,?,?,?)',
                           (pupil_id, dossier['sujet_id'], versions[item['version']], '', 'present')).lastrowid
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
WorkflowApplication.save_anonymity = _save_anonymity
WorkflowApplication.draft = _draft
WorkflowApplication.exchange = _exchange
WorkflowApplication._grid = _grid
