"""Render only: every displayed score is supplied by calcul.py."""
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from .notes import config_from_mapping


def tex_escape(value):
    replacements = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
                    '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}',
                    '^': r'\textasciicircum{}', '\n': r'\newline{}'}
    return ''.join(replacements.get(c, c) for c in str(value or ''))


def fmt(value):
    return 'ABS' if value is None else format(value, '.10g').replace('.', ',')


def build_student_data(conn, result, row):
    data = dict(row)
    data['items'] = []
    data['annotations'] = []
    data['conseils'] = []
    data['commentaire_global'] = None
    data['corrige_latex'] = None
    if row['version_id'] is not None:
        corrige = conn.execute('SELECT str_latex FROM corrige WHERE version_id=?', (row['version_id'],)).fetchone()
        if corrige:
            data['corrige_latex'] = corrige['str_latex']
    if row['correction_id'] is not None:
        cid = row['correction_id']
        data['commentaire_global'] = conn.execute('SELECT commentaire_global FROM correction WHERE id=?', (cid,)).fetchone()[0]
        data['items'] = [dict(r) for r in conn.execute('''SELECT i.code,i.description,i.bareme_max,
            e.numero exercice,q.numero question,ci.points_obtenus,ci.statut,ci.commentaire,ci.annotation
            FROM correction_item ci JOIN item i ON i.id=ci.item_id JOIN question q ON q.id=i.question_id
            JOIN exercice e ON e.id=q.exercice_id WHERE ci.correction_id=? ORDER BY e.ordre,q.ordre,i.ordre,i.id''', (cid,))]
        for table in ('annotations', 'conseils'):
            singular = 'annotation' if table == 'annotations' else 'conseil'
            ordering = 't.page,t.id' if table == 'annotations' else 'COALESCE(t.priorite,999),t.id'
            data[table] = [{k: r[k] for k in r.keys() if k not in {'id', 'correction_id', 'item_id'}} for r in conn.execute(f'''SELECT t.*,i.code item_code FROM {singular} t
                LEFT JOIN item i ON i.id=t.item_id WHERE t.correction_id=? ORDER BY {ordering}''', (cid,))]
    return data


def render_student(student, subject, cfg):
    esc = tex_escape
    individual_only = cfg.groupe_mode == 'aucun' or cfg.note_groupe_max == 0
    lines = [r'\documentclass[11pt,a4paper]{article}', r'\usepackage[utf8]{inputenc}',
             r'\usepackage[T1]{fontenc}', r'\usepackage{lmodern}', r'\IfFileExists{french.ldf}{\usepackage[french]{babel}}{}', r'\usepackage{amsmath,amssymb,longtable,array}',
             r'\usepackage[margin=18mm]{geometry}', r'\setlength{\parindent}{0pt}', r'\setlength{\parskip}{5pt}',
             r'\begin{document}', r'{\Large\bfseries '+esc(subject.get('titre') or 'Évaluation')+r'}\par',
             esc(f"{subject['classe']} - {student.get('label') or ('Élève n° ' + str(student['numero']))} - Version {student['version'] or '?'}"),
             r'\par\vspace{4mm}\renewcommand{\arraystretch}{1.5}']
    if individual_only:
        lines += [r'\begin{tabular}{|p{.40\linewidth}|}\hline',
                  f"Note (/{fmt(cfg.note_finale_max)})"+r'\\\hline',
                  fmt(student['note_finale'])+r'\\\hline',
                  r'\end{tabular}']
    else:
        peers = '; '.join(f"n° {p['numero']} : {fmt(p['note_individuelle'])}" + (' (absent)' if p['statut']=='absent' else '') for p in student['camarades']) or 'Aucun camarade'
        lines += [r'\begin{tabular}{|p{.28\linewidth}|p{.36\linewidth}|p{.23\linewidth}|}\hline',
                  f"Note interro (/{fmt(cfg.note_individuelle_max)}) & Note groupe (/{fmt(cfg.note_groupe_max)}) & Note finale (/{fmt(cfg.note_finale_max)})"+r'\\\hline',
                  f"{fmt(student['note_individuelle'])} & {fmt(student['note_groupe'])}" +
                  r'\newline{\scriptsize '+esc(peers+f' (/{fmt(cfg.note_individuelle_max)})')+r'} & '+fmt(student['note_finale'])+r'\\\hline',
                  r'\end{tabular}']
    if student['statut'] == 'absent':
        lines += [r'\par\textbf{Absence déclarée.}']
    else:
        lines += [r'\section*{Bilan par item}', r'\renewcommand{\arraystretch}{1.15}',
                  r'\begin{longtable}{p{.17\linewidth}p{.60\linewidth}r}',
                  r'\textbf{Item} & \textbf{Critère et retour} & \textbf{Points}\\\hline\endhead']
        for item in student['items']:
            detail = esc(item['description'])
            for key in ('annotation', 'commentaire'):
                if item[key]:
                    detail += r'\newline{\small '+esc(item[key])+'}'
            lines.append(esc(item['code'])+' & '+detail+' & '+fmt(item['points_obtenus'])+'/'+fmt(item['bareme_max'])+r'\\')
        lines += [r'\end{longtable}']
        if student['commentaire_global']:
            lines += [esc(student['commentaire_global'])]
    if student['annotations']:
        lines += [r'\section*{Annotations de la copie}', r'\begin{itemize}']
        for a in student['annotations']:
            lines += [r'\item '+esc(f"Page {a['page']} - {a['item_code']} : {a['texte']}")]
        lines += [r'\end{itemize}']
    if student['conseils']:
        lines += [r'\section*{Conseils}', r'\begin{itemize}']
        lines += [r'\item '+esc(a['texte']) for a in student['conseils']]
        lines += [r'\end{itemize}']
    if student['corrige_latex']:
        lines += [r'\section*{Corrigé}', student['corrige_latex']]
    lines += [r'\end{document}', '']
    return '\n'.join(lines)


def compile_pdf(tex_path, timeout=60):
    engine = shutil.which('pdflatex')
    if not engine:
        raise RuntimeError('pdflatex introuvable ; installer TeX Live avec le français ou omettre --pdf')
    tex_path = Path(tex_path).resolve()
    env = dict(os.environ, openin_any='p', openout_any='p')
    for _ in range(2):
        try:
            run = subprocess.run([engine, '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error', tex_path.name],
                                 cwd=tex_path.parent, env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f'Compilation trop longue : {tex_path.name}') from exc
        if run.returncode:
            raise RuntimeError(f'Compilation échouée : {tex_path.name}\n{run.stdout[-2500:]}')
    pdf = tex_path.with_suffix('.pdf')
    if not pdf.is_file():
        raise RuntimeError('Aucun PDF produit')
    return pdf


def export_grids(conn, sujet_id, directory):
    for grid in conn.execute('SELECT * FROM grille WHERE sujet_id=? ORDER BY id', (sujet_id,)):
        lines = [f"# Grille - {grid['nom'] or grid['id']}", '',
                 f"- Sujet : {sujet_id}", f"- Grille SQLite : {grid['id']}",
                 f"- Validée : {'oui' if grid['valide'] else 'non'}",
                 f"- Total : {fmt(grid['total_points'])}", '']
        current_ex, current_q = None, None
        for item in conn.execute('''SELECT i.*,e.id eid,e.numero ex,e.titre,q.id qid,q.numero q
            FROM item i JOIN question q ON q.id=i.question_id JOIN exercice e ON e.id=q.exercice_id
            WHERE i.grille_id=? ORDER BY e.ordre,q.ordre,i.ordre''', (grid['id'],)):
            if item['eid'] != current_ex:
                lines += [f"## Exercice {item['ex']} - {item['titre'] or ''}", '']
                current_ex = item['eid']
            if item['qid'] != current_q:
                lines += [f"### Question {item['q']}", '']
                current_q = item['qid']
            lines += [f"- `{item['code']}` - {item['description']} - {fmt(item['bareme_max'])} pt"]
            if item['regle_correction']:
                lines += [f"  - Règle : {item['regle_correction']}"]
        (directory/f"grille_{grid['id']}.md").write_text('\n'.join(lines)+'\n', encoding='utf-8')


def export_results(conn, result, output, pdf=False, combined=False):
    """Build in a fresh directory; never expose partial or stale exports as a success."""
    output = Path(output).resolve()
    if output.exists():
        raise ValueError(f'Le dossier de sortie existe déjà : {output} ; choisir un nouveau dossier')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.smartcorrection-', dir=output.parent))
    cfg = config_from_mapping(result['config'])
    try:
        export_grids(conn, result['sujet']['id'], stage)
        students = [build_student_data(conn, result, row) for row in result['notes']]
        payload = dict(result, fiches=students)
        (stage/'notes.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        fields = ['copie_id','numero','statut','groupe','note_brute','bareme_max','note_individuelle','note_groupe','note_finale','camarades']
        with (stage/'notes.csv').open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fields, delimiter=';')
            writer.writeheader()
            for student in students:
                row = {k: student[k] for k in fields}
                row['camarades'] = ' | '.join(f"{p['numero']}: {fmt(p['note_individuelle'])}" for p in student['camarades'])
                writer.writerow(row)
        for student in students:
            name = f"eleve_{student['numero']:03d}" if student['numero'] is not None else f"copie_{student['copie_id']:04d}"
            path = stage/f"{name}.tex"
            path.write_text(render_student(student, result['sujet'], cfg), encoding='utf-8')
            if pdf:
                compile_pdf(path)
        if pdf and combined:
            from pypdf import PdfWriter
            writer = PdfWriter()
            try:
                for path in sorted(stage.glob('*.pdf')):
                    writer.append(str(path))
                writer.write(str(stage/'corrections.pdf'))
            finally:
                writer.close()
        manifest = {'format_version': 1, 'sujet_id': result['sujet']['id'], 'pdf': pdf,
                    'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.iterdir()) if p.suffix in {'.json','.csv','.tex','.pdf','.md'}}}
        (stage/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
        for path in stage.iterdir():
            if path.suffix in {'.aux','.log','.out'}:
                path.unlink()
        stage.rename(output)
    except Exception:
        shutil.rmtree(stage)
        raise
    return output
