from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from .db import database, init_db


def _header_key(value: str) -> str:
    return value.strip().lower().replace(' ', '_')


def parse_pages(value: str) -> list[int]:
    text = (value or '').strip().replace('–', '-').replace('—', '-')
    if not text:
        return []
    pages: list[int] = []
    seen: set[int] = set()
    for token in re.split(r'[\s,]+', text):
        if not token:
            continue
        if '-' in token:
            parts = token.split('-')
            if len(parts) != 2:
                raise ValueError(f'Plage de pages invalide : {token!r}')
            try:
                start, end = (int(part) for part in parts)
            except ValueError as exc:
                raise ValueError(f'Plage de pages invalide : {token!r}') from exc
            if start <= 0 or end <= 0 or end < start:
                raise ValueError(f'Plage de pages invalide : {token!r}')
            values = range(start, end + 1)
        else:
            try:
                page = int(token)
            except ValueError as exc:
                raise ValueError(f'Numéro de page invalide : {token!r}') from exc
            if page <= 0:
                raise ValueError('Les numéros de page doivent être strictement positifs')
            values = (page,)
        for page in values:
            if page in seen:
                raise ValueError(f'Page répétée dans une copie : {page}')
            seen.add(page)
            pages.append(page)
    if pages != sorted(pages):
        raise ValueError('Les pages d’une copie doivent être indiquées dans l’ordre croissant')
    return pages


def _read_copies_csv(path) -> list[dict]:
    source = Path(path)
    text = source.read_text(encoding='utf-8-sig')
    if not text.strip():
        raise ValueError('CSV de copies vide')
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if reader.fieldnames is None:
        raise ValueError('Le CSV doit contenir une ligne d’en-tête')

    aliases = {
        'numero': 'numero', 'num': 'numero', 'n': 'numero',
        'version': 'version',
        'page': 'pages', 'pages': 'pages',
        'statut': 'statut', 'status': 'statut',
    }
    columns = {}
    for original in reader.fieldnames:
        key = aliases.get(_header_key(original))
        if key and key not in columns:
            columns[key] = original
    missing = {'numero', 'version', 'pages'} - set(columns)
    if missing:
        raise ValueError('Le CSV doit contenir les colonnes numero, version et pages')

    rows = []
    seen_numbers = set()
    for row_index, row in enumerate(reader, 2):
        if not any((value or '').strip() for value in row.values()):
            continue
        raw_num = (row.get(columns['numero']) or '').strip()
        try:
            numero = int(raw_num)
        except ValueError as exc:
            raise ValueError(f'Ligne {row_index} : numero invalide') from exc
        if numero <= 0:
            raise ValueError(f'Ligne {row_index} : numero doit être strictement positif')
        if numero in seen_numbers:
            raise ValueError(f'Numéro répété dans le CSV : {numero}')
        seen_numbers.add(numero)

        version = (row.get(columns['version']) or '').strip()
        if not version:
            raise ValueError(f'Ligne {row_index} : version manquante')
        status = (row.get(columns.get('statut', '')) or 'present').strip().lower()
        if status not in {'present', 'absent'}:
            raise ValueError(f'Ligne {row_index} : statut invalide')
        pages = parse_pages(row.get(columns['pages']) or '')
        if status == 'present' and not pages:
            raise ValueError(f'Ligne {row_index} : pages obligatoires pour une copie présente')
        if status == 'absent' and pages:
            raise ValueError(f'Ligne {row_index} : une absence ne doit pas avoir de pages')
        rows.append({'numero': numero, 'version': version, 'pages': pages, 'statut': status})
    if not rows:
        raise ValueError('Le CSV ne contient aucune copie')
    return rows


def import_copies_csv(path, sujet_id, pdf_path, db_path, replace=False):
    rows = _read_copies_csv(path)
    init_db(db_path)
    pdf = Path(pdf_path).resolve()
    if not pdf.is_file():
        raise ValueError(f'PDF introuvable : {pdf}')

    inserted = updated = reused = absent = 0
    assigned_pages = 0
    with database(db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        subject = conn.execute('SELECT id,classe FROM sujet WHERE id=?', (sujet_id,)).fetchone()
        if not subject:
            raise ValueError(f'Sujet inconnu : {sujet_id}')
        versions = {row['version']: row['id'] for row in conn.execute(
            'SELECT id,version FROM version WHERE sujet_id=?', (sujet_id,)
        )}
        pupils = {row['numero']: row['id'] for row in conn.execute(
            'SELECT id,numero FROM eleve WHERE classe=?', (subject['classe'],)
        )}

        for row in rows:
            numero = row['numero']
            if numero not in pupils:
                raise ValueError(f'Élève n°{numero} absent de la classe {subject["classe"]}')
            if row['version'] not in versions:
                raise ValueError(f'Version inconnue pour le sujet {sujet_id} : {row["version"]}')
            status = row['statut']
            desired_pdf = str(pdf) if status == 'present' else ''
            desired_version = versions[row['version']]
            existing = conn.execute(
                'SELECT * FROM copie WHERE sujet_id=? AND eleve_id=?',
                (sujet_id, pupils[numero]),
            ).fetchone()

            if existing:
                current_pages = [r['page'] for r in conn.execute(
                    'SELECT page FROM copie_page WHERE copie_id=? ORDER BY ordre', (existing['id'],)
                )]
                exact = (
                    existing['version_id'] == desired_version
                    and existing['pdf_path'] == desired_pdf
                    and existing['statut'] == status
                    and current_pages == row['pages']
                )
                if exact:
                    reused += 1
                    absent += int(status == 'absent')
                    assigned_pages += len(row['pages'])
                    continue
                if not replace:
                    raise ValueError(
                        f'Copie déjà associée pour l’élève n°{numero}; utiliser --replace avant toute correction'
                    )
                if conn.execute('SELECT 1 FROM correction WHERE copie_id=?', (existing['id'],)).fetchone():
                    raise ValueError(f'Copie n°{numero} déjà corrigée : association figée')
                conn.execute(
                    'UPDATE copie SET version_id=?,pdf_path=?,statut=? WHERE id=?',
                    (desired_version, desired_pdf, status, existing['id']),
                )
                conn.execute('DELETE FROM copie_page WHERE copie_id=?', (existing['id'],))
                copy_id = existing['id']
                updated += 1
            else:
                copy_id = conn.execute(
                    'INSERT INTO copie(eleve_id,sujet_id,version_id,pdf_path,statut) VALUES(?,?,?,?,?)',
                    (pupils[numero], sujet_id, desired_version, desired_pdf, status),
                ).lastrowid
                inserted += 1

            for order, page in enumerate(row['pages'], 1):
                conn.execute(
                    'INSERT INTO copie_page(copie_id,page,ordre) VALUES(?,?,?)',
                    (copy_id, page, order),
                )
            absent += int(status == 'absent')
            assigned_pages += len(row['pages'])

    return {
        'sujet_id': sujet_id,
        'pdf': str(pdf),
        'copies_importees': inserted,
        'copies_mises_a_jour': updated,
        'deja_presentes': reused,
        'absents': absent,
        'pages_assignees': assigned_pages,
    }
