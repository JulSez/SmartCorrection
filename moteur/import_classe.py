from __future__ import annotations

import csv
import io
import unicodedata
from pathlib import Path

from .db import database, init_db


def _header_key(value: str) -> str:
    value = unicodedata.normalize('NFKD', value.strip().lower())
    return ''.join(ch for ch in value if not unicodedata.combining(ch)).replace(' ', '_')


def _read_roster(path):
    source = Path(path)
    text = source.read_text(encoding='utf-8-sig')
    if not text.strip():
        raise ValueError('CSV de classe vide')

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if reader.fieldnames is None:
        raise ValueError('Le CSV doit contenir une ligne d’en-tête')

    aliases = {
        'numero': 'numero', 'num': 'numero', 'n': 'numero',
        'nom': 'nom',
        'prenom': 'prenom', 'prenoms': 'prenom',
    }
    columns = {}
    for original in reader.fieldnames:
        key = aliases.get(_header_key(original))
        if key and key not in columns:
            columns[key] = original

    if 'nom' not in columns or 'prenom' not in columns:
        raise ValueError('Le CSV doit contenir les colonnes nom et prenom (numero est facultatif)')

    rows = []
    seen_numbers = set()
    for row_index, row in enumerate(reader, 1):
        if not any((value or '').strip() for value in row.values()):
            continue
        nom = (row.get(columns['nom']) or '').strip()
        prenom = (row.get(columns['prenom']) or '').strip()
        if not nom or not prenom:
            raise ValueError(f'Ligne {row_index + 1} : nom et prenom sont obligatoires')

        if 'numero' in columns:
            raw = (row.get(columns['numero']) or '').strip()
            if not raw:
                raise ValueError(f'Ligne {row_index + 1} : numero manquant')
            try:
                numero = int(raw)
            except ValueError as exc:
                raise ValueError(f'Ligne {row_index + 1} : numero invalide') from exc
            if numero <= 0:
                raise ValueError(f'Ligne {row_index + 1} : numero doit être strictement positif')
        else:
            numero = len(rows) + 1

        if numero in seen_numbers:
            raise ValueError(f'Numéro répété dans le CSV : {numero}')
        seen_numbers.add(numero)
        rows.append({'numero': numero, 'nom': nom, 'prenom': prenom})

    if not rows:
        raise ValueError('Le CSV ne contient aucun élève')
    return rows


def import_classe_csv(path, classe, db_path):
    classe = str(classe).strip()
    if not classe:
        raise ValueError('Le nom de classe est obligatoire')
    roster = _read_roster(path)
    init_db(db_path)

    inserted = 0
    reused = 0
    with database(db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        for pupil in roster:
            existing = conn.execute(
                'SELECT id,nom,prenom FROM eleve WHERE classe=? AND numero=?',
                (classe, pupil['numero']),
            ).fetchone()
            if existing:
                current_nom = (existing['nom'] or '').strip()
                current_prenom = (existing['prenom'] or '').strip()
                if current_nom and current_nom != pupil['nom']:
                    raise ValueError(
                        f"Conflit pour {classe} n°{pupil['numero']} : nom existant {current_nom!r}, CSV {pupil['nom']!r}"
                    )
                if current_prenom and current_prenom != pupil['prenom']:
                    raise ValueError(
                        f"Conflit pour {classe} n°{pupil['numero']} : prénom existant {current_prenom!r}, CSV {pupil['prenom']!r}"
                    )
                if not current_nom or not current_prenom:
                    conn.execute(
                        'UPDATE eleve SET nom=?,prenom=? WHERE id=?',
                        (pupil['nom'], pupil['prenom'], existing['id']),
                    )
                reused += 1
            else:
                conn.execute(
                    'INSERT INTO eleve(classe,numero,nom,prenom) VALUES(?,?,?,?)',
                    (classe, pupil['numero'], pupil['nom'], pupil['prenom']),
                )
                inserted += 1

        pupils = [dict(row) for row in conn.execute(
            'SELECT numero,nom,prenom FROM eleve WHERE classe=? ORDER BY numero', (classe,)
        )]

    return {
        'classe': classe,
        'importes': inserted,
        'deja_presents': reused,
        'effectif': len(pupils),
        'eleves': pupils,
    }
