"""Local group configuration for the GUI; no roster data enters AI prompts."""
import json
import re

GROUPS = {'note_individuelle': {'max': 15},
          'note_groupe': {'max': 5, 'mode': 'moyenne_camarades', 'sans_camarades': 'erreur'},
          'note_finale': {'max': 20, 'arrondi': .5}, 'absences': {'mode': 'exclure'}}


def group_state(conn, dossier):
    subject = conn.execute('SELECT config_notes FROM sujet WHERE id=?', (dossier['sujet_id'],)).fetchone()
    cfg = json.loads(subject[0]) if subject else {}
    members = [dict(r) for r in conn.execute('''SELECT g.numero_groupe,e.id numero,e.nom,e.prenom
        FROM groupe g JOIN groupe_eleve ge ON ge.groupe_id=g.id JOIN eleve e ON e.id=ge.eleve_id
        WHERE g.sujet_id=? ORDER BY g.numero_groupe,e.id''', (dossier['sujet_id'],))]
    assigned = {m['numero'] for m in members}
    missing = [r[0] for r in conn.execute('SELECT id FROM eleve_par_classe WHERE classe=? ORDER BY id',
                                        (dossier['classe'],)) if r[0] not in assigned]
    return {'actif': cfg.get('note_groupe', {}).get('max', 0) > 0,
            'membres': members, 'sans_groupe': missing}


def save_groups(conn, dossier, active, text, individual):
    if type(active) is not bool or not isinstance(text, str):
        raise ValueError('Option et liste des groupes invalides')
    if not dossier['sujet_id']:
        raise ValueError('Enregistrez d’abord la grille')
    pupils = {r['numero']: r['id'] for r in conn.execute('SELECT id,id numero FROM eleve_par_classe WHERE classe=?', (dossier['classe'],))}
    entries, seen = [], set()
    for line in text.splitlines():
        if not line.strip():
            continue
        tokens = re.split(r'[,;\s]+', line.strip())
        if any(not t.isascii() or not t.isdigit() for t in tokens):
            raise ValueError('Une ligne par groupe, avec les numéros séparés par des virgules ou espaces')
        nums = [int(t) for t in tokens]
        for num in nums:
            if num not in pupils:
                raise ValueError(f'Élève inconnu dans cette classe : {num}')
            if num in seen:
                raise ValueError(f'Élève présent plusieurs fois : {num}')
            seen.add(num)
        entries.append(nums)
    sid = dossier['sujet_id']
    conn.execute('DELETE FROM groupe WHERE sujet_id=?', (sid,))
    for n, nums in enumerate(entries, 1):
        gid = conn.execute('INSERT INTO groupe(sujet_id,numero_groupe) VALUES(?,?)', (sid,n)).lastrowid
        for num in nums:
            conn.execute('INSERT INTO groupe_eleve VALUES(?,?)', (gid,pupils[num]))
    conn.execute('UPDATE sujet SET config_notes=? WHERE id=?', (json.dumps(GROUPS if active else individual),sid))
    conn.execute('UPDATE correction SET note_finale=NULL WHERE copie_id IN (SELECT id FROM copie WHERE sujet_id=?)', (sid,))
    conn.execute('UPDATE ui_rendu SET valide=0 WHERE dossier_id=?', (dossier['id'],))
    conn.execute('UPDATE ui_dossier SET termine=0 WHERE id=?', (dossier['id'],))
    return group_state(conn,dossier)


def copy_groups(conn, old_sid, new_sid):
    if not old_sid:
        return
    cfg = conn.execute('SELECT config_notes FROM sujet WHERE id=?', (old_sid,)).fetchone()[0]
    conn.execute('UPDATE sujet SET config_notes=? WHERE id=?', (cfg,new_sid))
    for group in conn.execute('SELECT * FROM groupe WHERE sujet_id=?', (old_sid,)).fetchall():
        gid = conn.execute('INSERT INTO groupe(sujet_id,numero_groupe) VALUES(?,?)', (new_sid,group['numero_groupe'])).lastrowid
        conn.execute('INSERT INTO groupe_eleve SELECT ?,eleve_id FROM groupe_eleve WHERE groupe_id=?', (gid,group['id']))
