"""PR25: tolerate missing identities and let the teacher assign copies locally."""
from __future__ import annotations

import json
import re

from .db import database
from .validation import array, integer, object_fields, string
from . import pr20_patch as previous

WorkflowApplication = previous.WorkflowApplication
_BASE_STATE = WorkflowApplication.state
_BASE_REVIEW = WorkflowApplication.review


def _validate_preprocessing(data, dossier, anonymous=True):
    keys = {'dossier', 'revision', 'copies', 'pages_ignorees', 'absents'}
    object_fields(data, keys, {'dossier', 'revision', 'copies', 'pages_ignorees'})
    if data['dossier'] != dossier['id'] or type(data['revision']) is not int or data['revision'] != dossier['revision']:
        raise ValueError('Cette réponse vise un autre dossier ou une ancienne grille. Recopier la consigne actuelle.')
    refs, pages = set(), set()
    clean_copies = []
    for item in array(data['copies'], 'copies', True):
        allowed = {'reference', 'numero', 'version', 'pages'} if anonymous else {'reference', 'numero', 'version', 'pages', 'nom', 'prenom'}
        required = {'reference', 'numero', 'version', 'pages'}
        object_fields(item, allowed, required)
        ref = string(item['reference'], 'reference').strip()
        if not re.fullmatch(r'C\d{3,6}', ref) or ref in refs:
            raise ValueError('Référence de copie répétée ou invalide : utiliser C001, C002…')
        refs.add(ref)
        if item['numero'] is not None:
            raise ValueError('Le prétraitement initial ne doit contenir aucun numéro d’élève : utiliser null')
        version = string(item['version'], 'version').strip()
        checked = []
        for page in array(item['pages'], 'pages', True):
            page = integer(page, 'page')
            if page < 1 or page in pages:
                raise ValueError(f'Page {page} invalide ou attribuée deux fois')
            pages.add(page); checked.append(page)
        if checked != sorted(checked):
            raise ValueError('Indiquer les pages dans l’ordre du paquet')
        clean = {'reference': ref, 'numero': None, 'version': version, 'pages': checked}
        if not anonymous:
            clean['nom'] = previous._clean_name(item.get('nom'), 'nom')
            clean['prenom'] = previous._clean_name(item.get('prenom'), 'prenom')
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
            'pages_ignorees': ignored, 'absents': []}


def _match_student(conn, dossier, item):
    manual = item.get('eleve_id')
    if manual is not None:
        row = conn.execute('SELECT id FROM eleve_par_classe WHERE classe=? AND id=?', (dossier['classe'], manual)).fetchone()
        return row['id'] if row else None
    return previous._match_student_original(conn, dossier, item)


def _state(self, ident):
    result = _BASE_STATE(self, ident)
    with database(self.db_path) as conn:
        dossier = self._dossier(conn, ident)
        result['eleves'] = [dict(r) for r in conn.execute(
            'SELECT id,nom,prenom FROM eleve_par_classe WHERE classe=? ORDER BY nom COLLATE NOCASE,prenom COLLATE NOCASE,id',
            (dossier['classe'],)
        )]
        prep = result.get('pretraitement')
        if prep:
            for item in prep.get('copies', []):
                if item.get('eleve_id') is None:
                    guessed = previous._match_student_original(conn, dossier, item)
                    if guessed is not None:
                        item['eleve_id'] = guessed
    return result


def _assign_student(self, ident, reference, eleve_id=None):
    if not re.fullmatch(r'C\d{3,6}', reference or ''):
        raise ValueError('Référence de copie invalide')
    with database(self.db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        dossier = self._dossier(conn, ident)
        prep = previous._read_preprocessing(conn, ident)
        if not prep:
            raise ValueError('Valider d’abord les résultats de l’initialisation')
        target = next((c for c in prep.get('copies', []) if c.get('reference') == reference), None)
        if not target:
            raise ValueError('Copie inconnue')
        if eleve_id is not None:
            student = conn.execute('SELECT id,nom,prenom FROM eleve_par_classe WHERE classe=? AND id=?',
                                   (dossier['classe'], eleve_id)).fetchone()
            if not student:
                raise ValueError('Cet élève n’appartient pas à la classe')
            for other in prep.get('copies', []):
                if other is not target and other.get('eleve_id') == eleve_id:
                    raise ValueError('Cet élève est déjà affecté à une autre copie')
            target['eleve_id'] = eleve_id
            target['nom'] = student['nom']; target['prenom'] = student['prenom']
        else:
            target.pop('eleve_id', None)
            if not previous._anonymity(conn, ident):
                target['nom'] = None; target['prenom'] = None
        conn.execute('UPDATE ui_meta SET valeur=? WHERE cle=?',
                     (json.dumps(prep, ensure_ascii=False), previous._meta_key(ident)))
        linked = conn.execute('''SELECT c.id FROM ui_copie u JOIN copie c ON c.id=u.copie_id
                                 WHERE u.dossier_id=? AND u.reference=?''', (ident, reference)).fetchone()
        if linked:
            conn.execute('UPDATE copie SET eleve_id=? WHERE id=?', (eleve_id, linked['id']))
    return {'reference': reference, 'eleve_id': eleve_id}


def _review(self, ident, reference):
    if isinstance(reference, str) and reference.startswith('@affectation:'):
        parts = reference.split(':', 2)
        if len(parts) != 3:
            raise ValueError('Affectation invalide')
        copy_ref, raw = parts[1], parts[2]
        eleve_id = None if raw == '' else int(raw)
        return _assign_student(self, ident, copy_ref, eleve_id)
    return _BASE_REVIEW(self, ident, reference)


previous._match_student_original = previous._match_student
previous._validate_preprocessing = _validate_preprocessing
previous._match_student = _match_student
WorkflowApplication.state = _state
WorkflowApplication.assign_student = _assign_student
WorkflowApplication.review = _review
