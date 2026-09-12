from __future__ import annotations
from .db import database
from .notes import compute_raw_score
from .validation import array, integer, load_json, number, object_fields, string


def compatible_grid(conn, copy):
    grids = conn.execute('''SELECT * FROM grille WHERE sujet_id=? AND
        (version_id IS NULL OR version_id=?) ORDER BY version_id IS NULL, id''',
        (copy['sujet_id'], copy['version_id'])).fetchall()
    if not grids:
        raise ValueError('Aucune grille compatible')
    return grids[0]['id']


def import_correction(data, conn, replace=False):
    object_fields(data, {'copie_id', 'grille_id', 'items', 'conseils', 'annotations', 'commentaire_global'},
                  {'copie_id', 'grille_id', 'items'})
    copy_id = integer(data['copie_id'], 'copie_id')
    grid_id = integer(data['grille_id'], 'grille_id')
    copy = conn.execute('SELECT * FROM copie WHERE id=?', (copy_id,)).fetchone()
    grid = conn.execute('SELECT * FROM grille WHERE id=?', (grid_id,)).fetchone()
    if not copy or not grid or copy['statut'] != 'present' or not grid['valide']:
        raise ValueError('Copie absente/inconnue ou grille non validée/inconnue')
    if copy['sujet_id'] != grid['sujet_id'] or (grid['version_id'] is not None and grid['version_id'] != copy['version_id']):
        raise ValueError('La grille ne correspond pas au sujet/version de la copie')
    items = {r['code']: r for r in conn.execute('SELECT * FROM item WHERE grille_id=?', (grid_id,))}
    entries = array(data['items'], 'items', True)
    codes = []
    for entry in entries:
        object_fields(entry, {'item_code', 'points_obtenus', 'statut', 'annotation', 'commentaire'}, {'item_code', 'points_obtenus'})
        code = string(entry['item_code'])
        if code not in items:
            raise ValueError(f'Item extérieur à la grille : {code}')
        codes.append(code)
        points = number(entry['points_obtenus'], f'points {code}')
        if points > items[code]['bareme_max']:
            raise ValueError(f'Points supérieurs au barème : {code}')
        if entry.get('statut') is not None and (not isinstance(entry['statut'], str) or entry['statut'] not in {'acquis', 'partiel', 'non_acquis', 'non_repondu'}):
            raise ValueError(f'Statut inconnu : {code}')
        for key in ('annotation', 'commentaire'):
            string(entry.get(key), key, nullable=True)
    if len(set(codes)) != len(codes) or set(codes) != set(items):
        raise ValueError(f'Items répétés ou manquants : {sorted(set(items)-set(codes))}')
    string(data.get('commentaire_global'), nullable=True)
    old = conn.execute('SELECT id FROM correction WHERE copie_id=?', (copy_id,)).fetchone()
    if old and not replace:
        raise ValueError('Correction déjà présente ; remplacement explicite requis')
    if old:
        cid = old['id']
        for table in ('annotation', 'conseil', 'correction_item'):
            conn.execute(f'DELETE FROM {table} WHERE correction_id=?', (cid,))
        conn.execute('UPDATE correction SET grille_id=?,commentaire_global=?,note_brute=NULL,note_finale=NULL WHERE id=?',
                     (grid_id, data.get('commentaire_global'), cid))
    else:
        cid = conn.execute('INSERT INTO correction(copie_id,grille_id,commentaire_global) VALUES(?,?,?)',
                           (copy_id, grid_id, data.get('commentaire_global'))).lastrowid
    for entry in entries:
        conn.execute('''INSERT INTO correction_item(correction_id,item_id,points_obtenus,statut,annotation,commentaire)
            VALUES(?,?,?,?,?,?)''', (cid, items[entry['item_code']]['id'], entry['points_obtenus'], entry.get('statut'), entry.get('annotation'), entry.get('commentaire')))
    def item_id(entry, required=False):
        code = entry.get('item_code')
        if code is None and not required:
            return None
        string(code, 'item_code')
        if code not in items:
            raise ValueError(f'Référence extérieure à la grille : {code}')
        return items[code]['id']
    for advice in array(data.get('conseils', []), 'conseils'):
        object_fields(advice, {'item_code', 'texte', 'priorite'}, {'texte'})
        priority = advice.get('priorite')
        if priority is not None:
            integer(priority, 'priorite')
        conn.execute('INSERT INTO conseil(correction_id,item_id,texte,priorite) VALUES(?,?,?,?)',
                     (cid, item_id(advice), string(advice['texte']), priority))
    for annotation in array(data.get('annotations', []), 'annotations'):
        object_fields(annotation, {'item_code', 'page', 'x', 'y', 'largeur', 'hauteur', 'texte', 'type_annotation'}, {'item_code', 'page', 'texte'})
        page = integer(annotation['page'], 'page')
        for key in ('x', 'y', 'largeur', 'hauteur'):
            if annotation.get(key) is not None and number(annotation[key], key) > 1:
                raise ValueError(f'{key} doit être entre 0 et 1')
        if (annotation.get('x') is None) != (annotation.get('y') is None):
            raise ValueError('Fournir x et y ensemble')
        if any(annotation.get(k) is not None for k in ('largeur', 'hauteur')) and annotation.get('x') is None:
            raise ValueError('Dimensions sans position')
        for pos, size in (('x','largeur'), ('y','hauteur')):
            if (annotation.get(pos) or 0) + (annotation.get(size) or 0) > 1:
                raise ValueError('Annotation hors page')
        string(annotation.get('type_annotation'), nullable=True)
        conn.execute('''INSERT INTO annotation(correction_id,item_id,page,x,y,largeur,hauteur,texte,type_annotation)
            VALUES(?,?,?,?,?,?,?,?,?)''', (cid, item_id(annotation, True), page, annotation.get('x'), annotation.get('y'), annotation.get('largeur'), annotation.get('hauteur'), string(annotation['texte']), annotation.get('type_annotation')))
    total, _ = compute_raw_score((e['points_obtenus'], items[e['item_code']]['bareme_max']) for e in entries)
    conn.execute('UPDATE correction SET note_brute=? WHERE id=?', (total, cid))
    # Any changed member may affect every peer's final score. Cached finals are invalidated.
    conn.execute('UPDATE correction SET note_finale=NULL WHERE copie_id IN (SELECT id FROM copie WHERE sujet_id=?)', (copy['sujet_id'],))
    return cid


def import_correction_json(path, db_path, replace=False):
    with database(db_path) as conn:
        return import_correction(load_json(path), conn, replace)
