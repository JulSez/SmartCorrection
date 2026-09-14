"""Load authoritative item scores and groups; compute all pupils in one snapshot."""
import json
from .db import database
from .notes import config_from_mapping, compute_raw_score, scale_score, _round_step, compute_group_score, compute_final_note
from .validation import integer


def calculate(conn, sujet_id):
    integer(sujet_id, 'sujet_id')
    subject = conn.execute('SELECT * FROM sujet WHERE id=?', (sujet_id,)).fetchone()
    if not subject:
        raise ValueError('Sujet inconnu')
    cfg = config_from_mapping(json.loads(subject['config_notes'] or '{}'))
    unassigned = conn.execute(
        'SELECT COUNT(*) FROM copie WHERE sujet_id=? AND eleve_id IS NULL', (sujet_id,)
    ).fetchone()[0]
    if unassigned:
        raise ValueError(f'{unassigned} copie(s) non attribuée(s) à un élève')
    copies = conn.execute('''SELECT c.*,e.numero,e.classe,v.version FROM copie c JOIN eleve e ON e.id=c.eleve_id
        LEFT JOIN version v ON v.id=c.version_id WHERE c.sujet_id=? ORDER BY e.numero''', (sujet_id,)).fetchall()
    if not copies:
        raise ValueError('Aucune copie pour ce sujet')
    results = {}
    for copy in copies:
        if copy['classe'] != subject['classe']:
            raise ValueError('Classe de copie incohérente')
        row = dict(copy)
        row.update(copie_id=copy['id'], note_brute=None, bareme_max=None, note_individuelle=None,
                   note_groupe=None, note_finale=None, correction_id=None, camarades=[], groupe=None)
        if copy['statut'] == 'absent':
            if cfg.absence == 'zero':
                row.update(note_individuelle=0., note_groupe=0., note_finale=0.)
        else:
            correction = conn.execute('SELECT * FROM correction WHERE copie_id=?', (copy['id'],)).fetchone()
            if not correction:
                raise ValueError(f"Copie non corrigée : élève {copy['numero']}")
            grid = conn.execute('SELECT * FROM grille WHERE id=?', (correction['grille_id'],)).fetchone()
            if not grid['valide'] or grid['sujet_id'] != sujet_id or (grid['version_id'] is not None and grid['version_id'] != copy['version_id']):
                raise ValueError('Grille incompatible ou non validée')
            expected = {r['id']: r['bareme_max'] for r in conn.execute('SELECT id,bareme_max FROM item WHERE grille_id=?', (grid['id'],))}
            scores = conn.execute('SELECT item_id,points_obtenus FROM correction_item WHERE correction_id=?', (correction['id'],)).fetchall()
            if not expected or {r['item_id'] for r in scores} != set(expected):
                raise ValueError(f"Correction incomplète : élève {copy['numero']}")
            raw, maximum = compute_raw_score((r['points_obtenus'], expected[r['item_id']]) for r in scores)
            individual = scale_score(raw, maximum, cfg.note_individuelle_max)
            individual = min(cfg.note_individuelle_max, _round_step(individual, cfg.individuel_arrondi, cfg.arrondi_mode))
            row.update(correction_id=correction['id'], grille_id=grid['id'], note_brute=raw,
                       bareme_max=maximum, note_individuelle=individual)
        results[copy['eleve_id']] = row
    groups = {}
    for g in conn.execute('''SELECT g.id,g.numero_groupe,ge.eleve_id FROM groupe g
        JOIN groupe_eleve ge ON ge.groupe_id=g.id WHERE g.sujet_id=? ORDER BY g.numero_groupe,ge.eleve_id''', (sujet_id,)):
        if g['eleve_id'] not in results:
            raise ValueError('Membre de groupe sans copie ni absence déclarée')
        if results[g['eleve_id']]['groupe'] is not None:
            raise ValueError('Élève présent dans plusieurs groupes')
        results[g['eleve_id']]['groupe'] = g['numero_groupe']
        groups.setdefault(g['id'], []).append(g['eleve_id'])
    for members in groups.values():
        for pupil_id in members:
            results[pupil_id]['camarades'] = [
                {'numero': results[p]['numero'], 'statut': results[p]['statut'],
                 'note_individuelle': results[p]['note_individuelle']} for p in members if p != pupil_id]
    for row in results.values():
        if row['statut'] == 'absent':
            continue
        values = [p['note_individuelle'] for p in row['camarades'] if p['note_individuelle'] is not None]
        if cfg.groupe_mode.endswith('_groupe'):
            values.append(row['note_individuelle'])
        if not values and cfg.groupe_mode != 'aucun' and cfg.note_groupe_max > 0:
            if cfg.sans_camarades == 'erreur':
                raise ValueError(f"Aucun camarade disponible : élève {row['numero']}")
            if cfg.sans_camarades == 'individuelle':
                values = [row['note_individuelle']]
        row['note_groupe'] = compute_group_score(values, cfg)
        row['note_finale'] = compute_final_note(row['note_individuelle'], row['note_groupe'], cfg)
    # Only write after the entire evaluation has passed validation.
    for row in results.values():
        if row['correction_id'] is not None:
            conn.execute('UPDATE correction SET note_brute=?,note_finale=? WHERE id=?',
                         (row['note_brute'], row['note_finale'], row['correction_id']))
    return {'sujet': dict(subject), 'config': json.loads(subject['config_notes'] or '{}'),
            'notes': list(results.values())}


def calculate_notes(db_path, sujet_id):
    with database(db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        return calculate(conn, sujet_id)


def _selection_individuals(conn, sujet_id, copie_ids):
    """Individual-only preview, including anonymous copies; never relax the full CLI gate."""
    subject = conn.execute('SELECT * FROM sujet WHERE id=?', (sujet_id,)).fetchone()
    if not subject:
        raise ValueError('Sujet inconnu')
    cfg = config_from_mapping(json.loads(subject['config_notes'] or '{}'))
    if not copie_ids or len(set(copie_ids)) != len(copie_ids):
        raise ValueError('Sélection de copies vide ou répétée')
    rows = []
    for cid in copie_ids:
        integer(cid, 'copie_id')
        copy = conn.execute('''SELECT c.*,e.numero,e.nom,e.prenom,v.version FROM copie c
            LEFT JOIN eleve e ON e.id=c.eleve_id LEFT JOIN version v ON v.id=c.version_id
            WHERE c.id=? AND c.sujet_id=?''', (cid, sujet_id)).fetchone()
        if not copy:
            raise ValueError('Copie extérieure à cette évaluation')
        row = dict(copy, copie_id=cid, camarades=[], groupe=None, correction_id=None,
                   note_brute=None, bareme_max=None, note_individuelle=None, note_groupe=None, note_finale=None)
        row['label'] = (f"Élève n° {copy['numero']} - {copy['prenom'] or ''} {copy['nom'] or ''}".strip()
                        if copy['numero'] is not None else f'Copie {cid} - élève non identifié')
        if copy['statut'] == 'absent':
            if cfg.absence == 'zero':
                row.update(note_individuelle=0., note_groupe=0., note_finale=0.)
        else:
            correction = conn.execute('SELECT * FROM correction WHERE copie_id=?', (cid,)).fetchone()
            if not correction:
                raise ValueError(f'Copie {cid} non corrigée')
            grid = conn.execute('SELECT * FROM grille WHERE id=?', (correction['grille_id'],)).fetchone()
            if not grid['valide'] or grid['sujet_id'] != sujet_id or (grid['version_id'] is not None and grid['version_id'] != copy['version_id']):
                raise ValueError('Grille incompatible')
            items = {r['id']: r['bareme_max'] for r in conn.execute('SELECT * FROM item WHERE grille_id=?', (grid['id'],))}
            scores = conn.execute('SELECT * FROM correction_item WHERE correction_id=?', (correction['id'],)).fetchall()
            if not items or set(items) != {r['item_id'] for r in scores}:
                raise ValueError(f'Copie {cid} : correction incomplète')
            raw, maximum = compute_raw_score((r['points_obtenus'], items[r['item_id']]) for r in scores)
            individual = min(cfg.note_individuelle_max, _round_step(scale_score(raw, maximum, cfg.note_individuelle_max), cfg.individuel_arrondi, cfg.arrondi_mode))
            row.update(correction_id=correction['id'], grille_id=grid['id'], note_brute=raw, bareme_max=maximum,
                       note_individuelle=individual, note_groupe=0., note_finale=compute_final_note(individual, 0, cfg))
        rows.append(row)
    return {'sujet': dict(subject), 'config': json.loads(subject['config_notes'] or '{}'), 'notes': rows}



def calculate_selection(conn, sujet_id, copie_ids, *, allow_groups=False):
    """Compute peers from the whole subject, not merely the sample being rendered."""
    subject = conn.execute('SELECT config_notes FROM sujet WHERE id=?', (sujet_id,)).fetchone()
    if not subject:
        raise ValueError('Sujet inconnu')
    cfg = config_from_mapping(json.loads(subject[0]))
    grouped = cfg.groupe_mode != 'aucun' and cfg.note_groupe_max > 0
    if grouped and not allow_groups:
        raise ValueError('Le rendu partiel exige une notation individuelle sans groupe')
    result = _selection_individuals(conn, sujet_id, copie_ids)
    if not grouped:
        return result
    cache = {r['copie_id']: r for r in result['notes']}
    for row in result['notes']:
        row.update(note_groupe=None, note_finale=None, etat_groupe=None)
        if row['statut'] == 'absent':
            continue
        groups = conn.execute('''SELECT g.id,g.numero_groupe FROM groupe g JOIN groupe_eleve ge ON ge.groupe_id=g.id
            WHERE g.sujet_id=? AND ge.eleve_id=?''', (sujet_id,row['eleve_id'])).fetchall()
        if len(groups) > 1:
            raise ValueError('Élève présent dans plusieurs groupes')
        if not groups:
            row['etat_groupe'] = 'À traiter : élève sans groupe ou non identifié'
            continue
        group = groups[0]
        row['groupe'] = group['numero_groupe']
        pending = False
        for peer in conn.execute('''SELECT e.numero,c.id,c.statut,co.id correction_id,u.a_revoir
            FROM groupe_eleve ge JOIN eleve e ON e.id=ge.eleve_id
            LEFT JOIN copie c ON c.eleve_id=e.id AND c.sujet_id=?
            LEFT JOIN correction co ON co.copie_id=c.id LEFT JOIN ui_copie u ON u.copie_id=c.id
            WHERE ge.groupe_id=? AND ge.eleve_id<>? ORDER BY e.numero''', (sujet_id,group['id'],row['eleve_id'])):
            score = None
            if peer['statut'] != 'absent':
                if not peer['correction_id'] or peer['a_revoir']:
                    pending = True
                else:
                    if peer['id'] not in cache:
                        cache[peer['id']] = _selection_individuals(conn,sujet_id,[peer['id']])['notes'][0]
                    score = cache[peer['id']]['note_individuelle']
            row['camarades'].append({'numero':peer['numero'],'statut':peer['statut'] or 'non repérée','note_individuelle':score})
        values = [p['note_individuelle'] for p in row['camarades']
                  if p['statut'] != 'absent' and p['note_individuelle'] is not None]
        if pending:
            row['etat_groupe'] = 'En attente : camarade non corrigé ou à revoir'
        elif not values:
            row['etat_groupe'] = 'À traiter : aucun camarade disponible'
        else:
            row['note_groupe'] = compute_group_score(values,cfg)
            row['note_finale'] = compute_final_note(row['note_individuelle'],row['note_groupe'],cfg)
    return result
