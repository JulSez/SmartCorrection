from __future__ import annotations
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from .db import DEFAULT_DB, database, init_db
from .import_classe import import_classe_csv
from .import_copies import import_copies_csv
from .import_correction import (
    import_correction,
    import_correction_json,
    import_corrections_json,
    compatible_grid,
)
from .import_evaluation import import_evaluation, import_evaluation_json
from .calcul import calculate, calculate_notes
from .notes import config_from_mapping, compute_final_note, compute_group_score
from .render import export_results
from .validation import array, integer, load_json, object_fields, string


def _configure_utf8_stdio():
    """Keep CLI JSON/error output Unicode-safe, including redirected PowerShell output."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is not None:
            reconfigure(encoding='utf-8')


def run_pipeline(manifest_path, db_path, output, pdf=False, replace=False, check_pdfs=False):
    path = Path(manifest_path).resolve()
    manifest = object_fields(load_json(path), {'evaluation', 'corrections'}, {'evaluation', 'corrections'})
    evaluation_path = path.parent/string(manifest['evaluation'])
    init_db(db_path)
    with database(db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        sid = import_evaluation(load_json(evaluation_path), conn, evaluation_path.parent, check_pdfs)
        seen = set()
        for entry in array(manifest['corrections'], 'corrections'):
            object_fields(entry, {'numero', 'file'}, {'numero', 'file'})
            num = integer(entry['numero'], 'numero')
            if num in seen:
                raise ValueError(f'Correction répétée dans le manifeste : {num}')
            seen.add(num)
            copy = conn.execute('''SELECT c.* FROM copie c JOIN eleve_par_classe e ON e.id=c.eleve_id AND e.classe=(SELECT classe FROM sujet WHERE id=c.sujet_id)
                WHERE c.sujet_id=? AND e.numero=?''', (sid, num)).fetchone()
            if not copy:
                raise ValueError(f'Aucune copie pour le numéro {num}')
            correction = load_json(path.parent/string(entry['file']))
            if 'copie_id' in correction or 'grille_id' in correction:
                raise ValueError('Dans un manifeste, omettre copie_id et grille_id : ils sont résolus depuis le numéro')
            correction = dict(correction, copie_id=copy['id'], grille_id=compatible_grid(conn, copy))
            import_correction(correction, conn, replace)
        result = calculate(conn, sid)
        export_results(conn, result, output, pdf)
    return sid


def ai_packet(conn, copy_id, classe_path=None, savoir_faire=()):
    copy = conn.execute('SELECT * FROM copie WHERE id=?', (copy_id,)).fetchone()
    if not copy or copy['statut'] != 'present':
        raise ValueError('Copie présente introuvable')
    gid = compatible_grid(conn, copy)
    grid = conn.execute('SELECT * FROM grille WHERE id=?', (gid,)).fetchone()
    if not grid['valide']:
        raise ValueError('Valider la grille avant de préparer une correction IA')
    version = conn.execute('SELECT * FROM version WHERE id=?', (copy['version_id'],)).fetchone()
    corrige = conn.execute('SELECT str_latex FROM corrige WHERE version_id=?', (copy['version_id'],)).fetchone()
    pupil = conn.execute('SELECT numero FROM eleve_par_classe WHERE id=? AND classe=(SELECT classe FROM sujet WHERE id=?)', (copy['eleve_id'],copy['sujet_id'])).fetchone() if copy['eleve_id'] else None
    pages = [row['page'] for row in conn.execute(
        'SELECT page FROM copie_page WHERE copie_id=? ORDER BY ordre', (copy_id,)
    )]
    items = [dict(r) for r in conn.execute('''SELECT i.code,i.description,i.bareme_max,i.regle_correction,
        e.numero exercice,q.numero question,q.texte FROM item i JOIN question q ON q.id=i.question_id
        JOIN exercice e ON e.id=q.exercice_id WHERE i.grille_id=? ORDER BY e.ordre,q.ordre,i.ordre''', (gid,))]
    source = {'pdf_path': copy['pdf_path'], 'pages': pages or None}
    page_rule = (
        'La copie est dans un PDF partagé : lire uniquement les pages indiquées dans source.pages '
        'et utiliser les numéros de page du PDF source dans annotations.page. '
        if pages else ''
    )
    return {'copie': dict(copy), 'eleve_numero': pupil['numero'] if pupil else None,
            'source': source, 'grille_id': gid,
            'version': dict(version) if version else None,
            'corrige_latex': corrige[0] if corrige else None, 'items': items,
            'memoire_classe': Path(classe_path).read_text(encoding='utf-8') if classe_path else None,
            'savoir_faire': [{'fichier': str(p), 'texte': Path(p).read_text(encoding='utf-8')} for p in savoir_faire],
            'consigne': page_rule + 'Produire uniquement le JSON du contrat docs/correction_format.md. Un score pour chaque item, aucun total. Ne pas inventer une réponse illisible : demander une revue humaine avant import.',
            'reponse_structure': {'copie_id': copy_id, 'grille_id': gid, 'items': [
                {'item_code': item['code'], 'points_obtenus': None, 'statut': None, 'commentaire': None, 'annotation': None}
                for item in items], 'annotations': [], 'conseils': [], 'commentaire_global': None}}


def ai_batch_packet(conn, sujet_id, classe_path=None, savoir_faire=()):
    """Prepare every present copy of one evaluation as a single AI correction batch."""
    subject = conn.execute('SELECT * FROM sujet WHERE id=?', (sujet_id,)).fetchone()
    if not subject:
        raise ValueError(f'Sujet inconnu : {sujet_id}')
    rows = conn.execute('''SELECT c.id, MIN(cp.page) AS first_page
        FROM copie c LEFT JOIN copie_page cp ON cp.copie_id=c.id
        WHERE c.sujet_id=? AND c.statut='present'
        GROUP BY c.id
        ORDER BY first_page IS NULL, first_page, c.id''', (sujet_id,)).fetchall()
    if not rows:
        raise ValueError('Aucune copie présente pour ce sujet')

    copies = []
    for row in rows:
        packet = ai_packet(conn, row['id'])
        copies.append({
            'copie_id': packet['copie']['id'],
            'eleve_numero': packet['eleve_numero'],
            'source': packet['source'],
            'grille_id': packet['grille_id'],
            'version': packet['version'],
            'corrige_latex': packet['corrige_latex'],
            'items': packet['items'],
            'reponse_structure': packet['reponse_structure'],
        })

    response = {
        'sujet_id': sujet_id,
        'corrections': [copy['reponse_structure'] for copy in copies],
    }
    return {
        'sujet': dict(subject),
        'sujet_id': sujet_id,
        'copies': copies,
        'memoire_classe': Path(classe_path).read_text(encoding='utf-8') if classe_path else None,
        'savoir_faire': [{'fichier': str(p), 'texte': Path(p).read_text(encoding='utf-8')} for p in savoir_faire],
        'consigne': (
            'Corriger toutes les copies présentes de ce lot. Pour chaque copie, lire uniquement source.pages '
            'dans son PDF source, appliquer sa grille/version et remplir exactement une correction. '
            'Retourner uniquement un objet JSON strict {"sujet_id": ..., "corrections": [...]}, sans total ni note finale. '
            'Chaque copie présente doit apparaître exactement une fois. Ne pas inventer une réponse illisible : demander une revue humaine avant import.'
        ),
        'reponse_structure': response,
    }


def build_parser():
    parser = argparse.ArgumentParser(prog='smartcorrection')
    sub = parser.add_subparsers(dest='command', required=True)
    for name, help_text in (
        ('init-db', 'Initialiser ou migrer SQLite'),
        ('import-classe', 'Importer une classe depuis un CSV'),
        ('import-copies', 'Associer les élèves aux pages d’un PDF partagé'),
        ('import-evaluation', 'Importer une évaluation complète'),
        ('import-correction', 'Importer une correction validée'),
        ('import-corrections', 'Importer atomiquement un lot complet de corrections'),
        ('calculate', 'Calculer les notes depuis SQLite'),
        ('render', 'Recalculer puis exporter les fiches'),
        ('run', 'Exécuter un manifeste complet'),
        ('prepare-ai', 'Préparer le contexte et le squelette de réponse IA'),
        ('validate-grid', 'Valider une grille après revue')):
        p = sub.add_parser(name, help=help_text)
        p.add_argument('--db', default=str(DEFAULT_DB))
        if name in {'import-classe', 'import-copies', 'import-evaluation', 'import-correction', 'import-corrections', 'run'}:
            p.add_argument('file')
        if name == 'import-classe':
            p.add_argument('--classe', required=True)
            p.add_argument('--preview', action='store_true', help='Proposer les rapprochements sans enregistrer')
            p.add_argument('--rapprochements', help='Fichier JSON avec empreinte et rapprochements validés')
        if name in {'import-copies', 'import-correction', 'import-corrections', 'run'}:
            p.add_argument('--replace', action='store_true')
        if name in {'import-evaluation', 'run'}:
            p.add_argument('--check-pdfs', action='store_true')
        if name in {'import-copies', 'calculate', 'render'}:
            p.add_argument('--sujet', type=int, required=True)
        if name == 'import-copies':
            p.add_argument('--pdf', required=True, help='PDF source commun aux copies du CSV')
        if name in {'render', 'run'}:
            p.add_argument('--output', required=True)
            p.add_argument('--pdf', action='store_true')
        if name == 'prepare-ai':
            target = p.add_mutually_exclusive_group(required=True)
            target.add_argument('--copie', type=int)
            target.add_argument('--sujet', type=int)
            p.add_argument('--classe-md')
            p.add_argument('--savoir-faire', nargs='*', default=[])
            p.add_argument('--output', help='Écrire le paquet JSON directement en UTF-8 dans ce fichier')
        if name == 'validate-grid':
            p.add_argument('--grille', type=int, required=True)
    gui = sub.add_parser('gui', help='Ouvrir l’interface graphique locale')
    gui.add_argument('--db', default=str(DEFAULT_DB))
    gui.add_argument('--data-dir', default='private/interface')
    gui.add_argument('--port', type=int, default=8765)
    gui.add_argument('--no-browser', action='store_true')
    p = sub.add_parser('note', help='Tester une configuration sans base')
    p.add_argument('--config')
    p.add_argument('--individual', type=float, required=True)
    p.add_argument('--peer', type=float, nargs='*', default=[])
    return parser


def main(argv=None):
    _configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        command = args.command
        if command == 'gui':
            from .gui import serve
            serve(args.db, args.data_dir, args.port, not args.no_browser)
            return 0
        if command == 'init-db':
            value = {'base': str(init_db(args.db))}
        elif command == 'import-classe':
            if args.preview:
                from .import_classe import _read_roster
                from .identites import preview_roster
                init_db(args.db)
                with database(args.db) as conn:
                    conn.execute('BEGIN')
                    value = preview_roster(conn,args.classe.strip(),_read_roster(args.file))
            else:
                decisions=load_json(args.rapprochements) if args.rapprochements else {}
                value = import_classe_csv(args.file, args.classe, args.db,
                                         choices=decisions.get('rapprochements'), fingerprint=decisions.get('empreinte'))
        elif command == 'import-copies':
            value = import_copies_csv(args.file, args.sujet, args.pdf, args.db, args.replace)
        elif command == 'import-evaluation':
            init_db(args.db)
            value = {'sujet_id': import_evaluation_json(args.file, args.db, args.check_pdfs)}
        elif command == 'import-correction':
            value = {'correction_id': import_correction_json(args.file, args.db, args.replace)}
        elif command == 'import-corrections':
            value = import_corrections_json(args.file, args.db, args.replace)
        elif command == 'calculate':
            value = calculate_notes(args.db, args.sujet)
        elif command == 'run':
            sid = run_pipeline(args.file, args.db, args.output, args.pdf, args.replace, args.check_pdfs)
            value = {'sujet_id': sid, 'output': str(Path(args.output).resolve())}
        elif command in {'render', 'prepare-ai', 'validate-grid'}:
            with database(args.db) as conn:
                conn.execute('BEGIN IMMEDIATE')
                if command == 'render':
                    value = {'output': str(export_results(conn, calculate(conn, args.sujet), args.output, args.pdf))}
                elif command == 'prepare-ai':
                    if args.copie is not None:
                        value = ai_packet(conn, args.copie, args.classe_md, args.savoir_faire)
                    else:
                        value = ai_batch_packet(conn, args.sujet, args.classe_md, args.savoir_faire)
                else:
                    row = conn.execute('SELECT SUM(bareme_max) FROM item WHERE grille_id=?', (args.grille,)).fetchone()
                    if row[0] is None or row[0] <= 0:
                        raise ValueError('Grille vide ou inconnue')
                    conn.execute('UPDATE grille SET valide=1,total_points=? WHERE id=? AND valide=0', (row[0],args.grille))
                    value = {'grille_id': args.grille, 'validee': True}
        else:
            cfg = config_from_mapping(load_json(args.config) if args.config else {})
            group = compute_group_score(args.peer, cfg)
            value = {'note_individuelle': args.individual, 'note_groupe': group,
                     'note_finale': compute_final_note(args.individual, group, cfg)}

        if command == 'prepare-ai' and args.output:
            output = Path(args.output).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
            if args.sujet is not None:
                value = {'sujet_id': args.sujet, 'copies': len(value['copies']), 'output': str(output)}
            else:
                value = {'copie_id': args.copie, 'output': str(output)}

        print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, sqlite3.Error, RuntimeError) as exc:
        print(f'Erreur : {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

