from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .db import database
from .notes import config_from_mapping
from .validation import array, integer, load_json, number, object_fields, string


def _optional_text(data, keys):
    for key in keys:
        if key in data:
            string(data[key], key, nullable=True)


def import_evaluation(data, conn, base_dir=Path('.'), check_pdfs=False):
    object_fields(data, {'cle', 'sujet', 'versions', 'grille', 'grilles', 'eleves', 'copies', 'groupes'}, {'sujet', 'versions'})
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    key = string(data.get('cle', digest), 'cle')
    previous = conn.execute('SELECT * FROM evaluation_import WHERE cle=?', (key,)).fetchone()
    if previous:
        if previous['empreinte'] != digest:
            raise ValueError('Cette clé désigne une évaluation différente ; utiliser une nouvelle clé')
        if check_pdfs:
            for copy in conn.execute("SELECT pdf_path FROM copie WHERE sujet_id=? AND statut='present'", (previous['sujet_id'],)):
                if not Path(copy['pdf_path']).is_file():
                    raise ValueError(f"PDF introuvable : {copy['pdf_path']}")
        return previous['sujet_id']
    subject = object_fields(data['sujet'], {'classe', 'chapitres', 'type', 'titre', 'date_evaluation', 'config_notes'}, {'classe'})
    classe = string(subject['classe'], 'classe')
    _optional_text(subject, ('chapitres', 'type', 'titre', 'date_evaluation'))
    config = subject.get('config_notes', {})
    config_from_mapping(config)
    subject_id = conn.execute('''INSERT INTO sujet(classe,chapitres,type,titre,date_evaluation,config_notes)
        VALUES(?,?,?,?,?,?)''', (classe, subject.get('chapitres'), subject.get('type'), subject.get('titre'),
        subject.get('date_evaluation'), json.dumps(config, ensure_ascii=False))).lastrowid
    versions = {}
    for v in array(data['versions'], 'versions', True):
        object_fields(v, {'version', 'str_latex', 'corrige_latex'}, {'version', 'str_latex'})
        label = string(v['version'], 'version')
        if label in versions:
            raise ValueError(f'Version répétée : {label}')
        vid = conn.execute('INSERT INTO version(sujet_id,version,str_latex) VALUES(?,?,?)',
                           (subject_id, label, string(v['str_latex'], 'str_latex'))).lastrowid
        versions[label] = vid
        if v.get('corrige_latex') is not None:
            conn.execute('INSERT INTO corrige(version_id,str_latex) VALUES(?,?)', (vid, string(v['corrige_latex'])))
    if ('grille' in data) == ('grilles' in data):
        raise ValueError('Fournir exactement grille ou grilles')
    grids = [data['grille']] if 'grille' in data else array(data['grilles'], 'grilles', True)
    for grid in grids:
        object_fields(grid, {'nom', 'version', 'validee', 'total_points', 'exercices'}, {'exercices'})
        _optional_text(grid, ('nom', 'version'))
        validated = grid.get('validee', False)
        if type(validated) is not bool:
            raise ValueError('validee doit être un booléen')
        version = grid.get('version')
        if version is not None and version not in versions:
            raise ValueError(f'Version de grille inconnue : {version}')
        gid = conn.execute('INSERT INTO grille(sujet_id,version_id,nom,valide) VALUES(?,?,?,?)',
                           (subject_id, versions.get(version), grid.get('nom'), int(validated))).lastrowid
        maxima = []
        for ei, ex in enumerate(array(grid['exercices'], 'exercices', True), 1):
            object_fields(ex, {'numero', 'titre', 'questions'}, {'numero', 'questions'})
            _optional_text(ex, ('titre',))
            eid = conn.execute('INSERT INTO exercice(grille_id,numero,titre,ordre) VALUES(?,?,?,?)',
                               (gid, string(ex['numero'], 'numero exercice'), ex.get('titre'), ei)).lastrowid
            for qi, q in enumerate(array(ex['questions'], 'questions', True), 1):
                object_fields(q, {'numero', 'texte', 'items'}, {'numero', 'items'})
                _optional_text(q, ('texte',))
                qid = conn.execute('INSERT INTO question(exercice_id,numero,texte,ordre) VALUES(?,?,?,?)',
                                   (eid, string(q['numero'], 'numero question'), q.get('texte'), qi)).lastrowid
                for ii, item in enumerate(array(q['items'], 'items', True), 1):
                    object_fields(item, {'code', 'description', 'bareme_max', 'regle_correction'}, {'code', 'description', 'bareme_max'})
                    maximum = number(item['bareme_max'], 'bareme_max')
                    _optional_text(item, ('regle_correction',))
                    conn.execute('''INSERT INTO item(question_id,grille_id,code,description,bareme_max,ordre,regle_correction)
                        VALUES(?,?,?,?,?,?,?)''', (qid, gid, string(item['code']), string(item['description']), maximum, ii, item.get('regle_correction')))
                    maxima.append(maximum)
        from .notes import compute_raw_score
        _, total = compute_raw_score((0, maximum) for maximum in maxima)
        number(total, 'total de grille', positive=True)
        if 'total_points' in grid and abs(number(grid['total_points']) - total) > 1e-9:
            raise ValueError('total_points diffère de la somme des items')
        conn.execute('UPDATE grille SET total_points=? WHERE id=?', (total, gid))

    pupils = {row['numero']: row['id'] for row in conn.execute(
        'SELECT id,numero FROM eleve WHERE classe=?', (classe,)
    )}
    declared = set()
    for pupil in array(data.get('eleves', []), 'eleves'):
        object_fields(pupil, {'numero', 'nom', 'prenom'}, {'numero'})
        num = integer(pupil['numero'], 'numero élève')
        if num in declared:
            raise ValueError(f'Élève répété : {num}')
        declared.add(num)
        _optional_text(pupil, ('nom', 'prenom'))
        conn.execute('INSERT INTO eleve(classe,numero,nom,prenom) VALUES(?,?,?,?) ON CONFLICT(classe,numero) DO NOTHING',
                     (classe, num, pupil.get('nom'), pupil.get('prenom')))
        pupils[num] = conn.execute('SELECT id FROM eleve WHERE classe=? AND numero=?', (classe, num)).fetchone()['id']
    for copy in array(data.get('copies', []), 'copies'):
        object_fields(copy, {'numero', 'version', 'pdf_path', 'statut'}, {'numero', 'version'})
        num = integer(copy['numero'], 'numero copie')
        version = string(copy['version'])
        if num not in pupils or version not in versions:
            raise ValueError('Copie : élève ou version non déclaré/importé dans la classe')
        status = copy.get('statut', 'present')
        if not isinstance(status, str) or status not in {'present', 'absent'}:
            raise ValueError('Statut de copie invalide')
        pdf = copy.get('pdf_path', '')
        if status == 'present':
            string(pdf, 'pdf_path')
        elif not isinstance(pdf, str):
            raise ValueError('pdf_path doit être un texte')
        pdf = str((Path(base_dir) / pdf).resolve()) if pdf else ''
        if check_pdfs and status == 'present' and not Path(pdf).is_file():
            raise ValueError(f'PDF introuvable : {pdf}')
        conn.execute('INSERT INTO copie(eleve_id,sujet_id,version_id,pdf_path,statut) VALUES(?,?,?,?,?)',
                     (pupils[num], subject_id, versions[version], pdf, status))
    for group in array(data.get('groupes', []), 'groupes'):
        object_fields(group, {'numero', 'eleves'}, {'numero', 'eleves'})
        gid = conn.execute('INSERT INTO groupe(sujet_id,numero_groupe) VALUES(?,?)',
                           (subject_id, integer(group['numero'], 'numero groupe'))).lastrowid
        for num in array(group['eleves'], 'membres', True):
            integer(num, 'numéro membre')
            if num not in pupils:
                raise ValueError(f'Membre non déclaré/importé dans la classe : {num}')
            conn.execute('INSERT INTO groupe_eleve(groupe_id,eleve_id) VALUES(?,?)', (gid, pupils[num]))
    conn.execute('INSERT INTO evaluation_import VALUES(?,?,?)', (key, digest, subject_id))
    return subject_id


def import_evaluation_json(path, db_path, check_pdfs=False):
    with database(db_path) as conn:
        return import_evaluation(load_json(path), conn, Path(path).resolve().parent, check_pdfs)
