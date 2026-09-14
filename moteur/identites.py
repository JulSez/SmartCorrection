"""Stable pupil identities, class membership and explicit import reconciliation."""
import hashlib
import json
import re
import unicodedata
from difflib import SequenceMatcher


def normalize(value):
    text=unicodedata.normalize('NFKD', value or '').casefold()
    return ' '.join(re.findall(r'[^\W_]+', ''.join(c for c in text if not unicodedata.combining(c))))


def similarity(left, right):
    a,b=normalize(left),normalize(right)
    if not a or not b:
        return 0
    if a==b:
        return 1
    aa,bb=set(a.split()),set(b.split())
    if aa<=bb or bb<=aa:
        return .93
    return SequenceMatcher(None,a,b).ratio()


def candidates(conn, nom, prenom):
    result=[]
    for pupil in conn.execute('SELECT * FROM eleve ORDER BY id'):
        names=[(pupil['nom'],pupil['prenom'])]+[tuple(r) for r in conn.execute('SELECT nom,prenom FROM eleve_nom_importe WHERE eleve_id=?',(pupil['id'],))]
        matches=[(similarity(nom,n),similarity(prenom,p)) for n,p in names]
        matches=[(n,p) for n,p in matches if n>=.72 and p>=.72 and (n+p)/2>=.82]
        if not matches:
            continue
        score=max((n+p)/2 for n,p in matches)
        result.append(dict(pupil,classes=[r[0] for r in conn.execute('SELECT classe FROM eleve_classe WHERE eleve_id=? ORDER BY classe',(pupil['id'],))],
                           raison='Nom et prénom concordants' if score==1 else 'Nom/prénom proche ou incomplet',score=round(score,3)))
    return sorted(result,key=lambda p:(-p['score'],p['id']))


def preview_roster(conn, classe, roster):
    rows=[]
    for i,pupil in enumerate(roster,1):
        matches=candidates(conn,pupil['nom'],pupil['prenom'])
        exact_here=[m for m in matches if classe in m['classes'] and m['score']==1]
        previous=[j for j,r in enumerate(roster[:i-1],1) if similarity(pupil['nom'],r['nom'])>=.82 and similarity(pupil['prenom'],r['prenom'])>=.82]
        rows.append(dict(pupil,ligne=i,candidats=matches,lignes_proches=previous,
                         inscrit_id=exact_here[0]['id'] if len(exact_here)==1 else None))
    population=[dict(p) for p in conn.execute('SELECT * FROM eleve ORDER BY id')]
    memberships=[tuple(r) for r in conn.execute('SELECT * FROM eleve_classe ORDER BY eleve_id,classe')]
    aliases=[tuple(r) for r in conn.execute('SELECT * FROM eleve_nom_importe ORDER BY eleve_id,nom,prenom')]
    token=hashlib.sha256(json.dumps([classe,roster,population,memberships,aliases],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return {'classe':classe,'eleves':rows,'empreinte':token,'identites':[dict(p,classes=[r[0] for r in conn.execute('SELECT classe FROM eleve_classe WHERE eleve_id=? ORDER BY classe',(p['id'],))]) for p in population]}


def add_membership(conn, pupil_id, classe, preferred):
    old=conn.execute('SELECT numero FROM eleve_classe WHERE eleve_id=? AND classe=?',(pupil_id,classe)).fetchone()
    if old:
        return old[0]
    used={r[0] for r in conn.execute('SELECT numero FROM eleve_classe WHERE classe=?',(classe,))}
    number=preferred if preferred not in used else max(used,default=0)+1
    conn.execute('INSERT INTO eleve_classe VALUES(?,?,?)',(pupil_id,classe,number))
    return number


def merge_pupils(conn, source, target):
    """Explicit teacher decision only; all links and the decision audit are transactional."""
    if source==target:
        return
    old=conn.execute('SELECT * FROM eleve WHERE id=?',(source,)).fetchone()
    if not old or not conn.execute('SELECT 1 FROM eleve WHERE id=?',(target,)).fetchone():
        raise ValueError('Identité introuvable : revérifiez le fichier')
    conflict=conn.execute('SELECT 1 FROM copie a JOIN copie b ON a.sujet_id=b.sujet_id WHERE a.eleve_id=? AND b.eleve_id=?',(source,target)).fetchone()
    groups=conn.execute('''SELECT 1 FROM groupe_eleve a JOIN groupe ga ON ga.id=a.groupe_id
        JOIN groupe gb ON gb.sujet_id=ga.sujet_id JOIN groupe_eleve b ON b.groupe_id=gb.id
        WHERE a.eleve_id=? AND b.eleve_id=? AND ga.id<>gb.id''',(source,target)).fetchone()
    if conflict or groups:
        raise ValueError('Fusion impossible : les deux IDs ont une copie ou des groupes différents pour la même évaluation. Les données restent intactes.')
    positions = {}
    for membership in conn.execute('SELECT * FROM eleve_classe WHERE eleve_id=?',(source,)).fetchall():
        if not conn.execute('SELECT 1 FROM eleve_classe WHERE eleve_id=? AND classe=?',(target,membership['classe'])).fetchone():
            positions[membership['classe']] = membership['numero']
        # The source still owns its old list position until references have moved.
        add_membership(conn,target,membership['classe'],membership['numero'])
    trigger=conn.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='freeze_copy_identity'").fetchone()[0]
    conn.execute('DROP TRIGGER freeze_copy_identity')
    try:
        conn.execute('UPDATE copie SET eleve_id=? WHERE eleve_id=?',(target,source))
    finally:
        conn.execute(trigger)
    conn.execute('INSERT OR IGNORE INTO groupe_eleve SELECT groupe_id,? FROM groupe_eleve WHERE eleve_id=?',(target,source))
    conn.execute('DELETE FROM groupe_eleve WHERE eleve_id=?',(source,))
    conn.execute('INSERT OR IGNORE INTO eleve_nom_importe SELECT ?,nom,prenom FROM eleve_nom_importe WHERE eleve_id=?',(target,source))
    if old['nom'] and old['prenom']:
        conn.execute('INSERT OR IGNORE INTO eleve_nom_importe VALUES(?,?,?)',(target,old['nom'],old['prenom']))
    conn.execute('INSERT INTO eleve_fusion(ancien_id,eleve_id,nom,prenom) VALUES(?,?,?,?)',(source,target,old['nom'],old['prenom']))
    conn.execute('UPDATE eleve_fusion SET eleve_id=? WHERE eleve_id=?',(target,source))
    conn.execute('DELETE FROM eleve_nom_importe WHERE eleve_id=?',(source,))
    conn.execute('DELETE FROM eleve_classe WHERE eleve_id=?',(source,))
    for classe,numero in positions.items():
        conn.execute('UPDATE eleve_classe SET numero=? WHERE eleve_id=? AND classe=?',(numero,target,classe))
    conn.execute('DELETE FROM eleve WHERE id=?',(source,))
    conn.execute('''UPDATE ui_rendu SET valide=0 WHERE dossier_id IN
        (SELECT d.id FROM ui_dossier d JOIN copie c ON c.sujet_id=d.sujet_id WHERE c.eleve_id=?)''',(target,))
    conn.execute('UPDATE ui_dossier SET termine=0 WHERE sujet_id IN (SELECT sujet_id FROM copie WHERE eleve_id=?)',(target,))


def commit_roster(conn, classe, roster, choices=None, fingerprint=None):
    preview=preview_roster(conn,classe,roster)
    if fingerprint is not None and fingerprint!=preview['empreinte']:
        raise ValueError('Le fichier ou les identités ont changé. Vérifiez de nouveau le fichier.')
    if choices is not None and (not isinstance(choices,list) or len(choices)!=len(roster)):
        raise ValueError('Une décision est nécessaire pour chaque ligne')
    inserted=reused=0;resolved={}
    for i,row in enumerate(preview['eleves']):
        choice=choices[i] if choices is not None else None
        if choice is None:
            if row['inscrit_id'] and len(row['candidats'])==1 and not row['lignes_proches']:
                choice={'id':row['inscrit_id']}
            elif row['candidats'] or row['lignes_proches']:
                raise ValueError(f"Ligne {i+1} : rapprochement à valider dans l’interface")
            else:
                choice={'nouveau':True}
        if not isinstance(choice,dict) or set(choice) not in ({'id'},{'nouveau'},{'ligne'},{'id','fusionner'}):
            raise ValueError('Décision de rapprochement invalide')
        if 'ligne' in choice:
            index=choice['ligne']
            if type(index) is not int or index not in resolved:
                raise ValueError('Le doublon doit désigner une ligne précédente')
            pupil_id=resolved[index];reused+=1
        elif 'id' in choice:
            pupil_id=choice['id']
            if type(pupil_id) is not int or not conn.execute('SELECT 1 FROM eleve WHERE id=?',(pupil_id,)).fetchone():
                raise ValueError('ID élève inconnu')
            if 'fusionner' in choice:
                if type(choice['fusionner']) is not int or choice['fusionner']!=row['inscrit_id']:
                    raise ValueError('La fusion doit viser l’identité de classe affichée lors de la vérification')
                merge_pupils(conn,choice['fusionner'],pupil_id)
            reused+=1
        else:
            if choice.get('nouveau') is not True:
                raise ValueError('Confirmer la création du nouvel élève')
            # Legacy CLI input cannot silently reuse a list number for another identity.
            if choices is None and conn.execute('SELECT 1 FROM eleve_classe WHERE classe=? AND numero=?',(classe,row['numero'])).fetchone():
                raise ValueError(f"Conflit de numéro de liste : {row['numero']}. Validez l’import dans l’interface.")
            pupil_id=conn.execute('INSERT INTO eleve(nom,prenom) VALUES(?,?)',(row['nom'],row['prenom'])).lastrowid
            inserted+=1
        add_membership(conn,pupil_id,classe,row['numero'])
        conn.execute('INSERT OR IGNORE INTO eleve_nom_importe VALUES(?,?,?)',(pupil_id,row['nom'],row['prenom']))
        # Enrich legacy placeholders without shortening an established name.
        conn.execute("UPDATE eleve SET nom=CASE WHEN nom IS NULL OR nom='' THEN ? ELSE nom END, prenom=CASE WHEN prenom IS NULL OR prenom='' THEN ? ELSE prenom END WHERE id=?",(row['nom'],row['prenom'],pupil_id))
        resolved[i+1]=pupil_id
    pupils=[dict(p) for p in conn.execute('SELECT e.id,e.id numero,e.nom,e.prenom FROM eleve e JOIN eleve_classe c ON c.eleve_id=e.id WHERE c.classe=? ORDER BY e.id',(classe,))]
    return {'classe':classe,'importes':inserted,'deja_presents':reused,'effectif':len(pupils),'eleves':pupils}
