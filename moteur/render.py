"""Render supplied scores; question subtotals are presentation-only sums."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
from contextvars import ContextVar
from decimal import Decimal
from .notes import config_from_mapping


_GRID_MODE = ContextVar('smartcorrection_grid_mode', default='questions')

_CORRECTION_PAGE_BREAK = ContextVar('smartcorrection_page_break_after_correction', default=True)

_MATH_SYMBOLS = {
    '×': r'\times', '÷': r'\div', '·': r'\cdot', '⋅': r'\cdot',
    '√': r'\sqrt{\phantom{x}}', '≤': r'\leq', '≥': r'\geq', '≠': r'\neq',
    '→': r'\rightarrow', '←': r'\leftarrow', '↔': r'\leftrightarrow',
    '⇒': r'\Rightarrow', '⇐': r'\Leftarrow', '⇔': r'\Leftrightarrow',
    '∞': r'\infty', '±': r'\pm', '∓': r'\mp', '≈': r'\approx', '≃': r'\simeq',
    '≡': r'\equiv', '∈': r'\in', '∉': r'\notin', '∅': r'\varnothing',
    '∪': r'\cup', '∩': r'\cap', '⊂': r'\subset', '⊆': r'\subseteq',
    '⊃': r'\supset', '⊇': r'\supseteq', '∀': r'\forall', '∃': r'\exists',
    '∑': r'\sum', '∏': r'\prod', '∫': r'\int', '∂': r'\partial',
    '∇': r'\nabla', '⊥': r'\perp', '∥': r'\parallel', '¬': r'\neg',
    '∧': r'\wedge', '∨': r'\vee', 'ℝ': r'\mathbb{R}', 'ℕ': r'\mathbb{N}',
    'ℤ': r'\mathbb{Z}', 'ℚ': r'\mathbb{Q}', 'ℂ': r'\mathbb{C}',
    'α': r'\alpha', 'β': r'\beta', 'γ': r'\gamma', 'δ': r'\delta',
    'ε': r'\varepsilon', 'θ': r'\theta', 'λ': r'\lambda', 'μ': r'\mu',
    'µ': r'\mu', 'π': r'\pi', 'ρ': r'\rho', 'σ': r'\sigma', 'τ': r'\tau',
    'φ': r'\varphi', 'ω': r'\omega', 'Δ': r'\Delta', 'Σ': r'\Sigma',
    'Π': r'\Pi', 'Ω': r'\Omega', '°': r'{}^{\circ}',
    '½': r'\frac{1}{2}', '¼': r'\frac{1}{4}', '¾': r'\frac{3}{4}',
}
_UNICODE_TEXT = {
    '−': '-', '‐': '-', '‑': '-', '–': '--', '—': '---',
    '‘': "'", '’': "'", '“': '``', '”': "''", '…': r'\ldots{}',
    '\u00a0': '~', '\u202f': '~', '\u2009': r'\,', '\u200b': '', '\ufeff': '',
    '«': r'\guillemotleft{}', '»': r'\guillemotright{}',
    '€': r'\texteuro{}', '£': r'\pounds{}',
}
_UNICODE_TEXT.update({c: r'\textsuperscript{'+n+'}' for c, n in zip('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789')})
_UNICODE_TEXT.update({c: r'\(_{'+n+r'}\)' for c, n in zip('₀₁₂₃₄₅₆₇₈₉', '0123456789')})


def latex_escape_plain_text(value):
    """Escape untrusted prose and emit pdflatex-safe Unicode equivalents.

    Combining macrons/vector arrows used in mathematical prose are converted to
    LaTeX commands instead of falling back to U+xxxx placeholders.
    """
    replacements = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
                    '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}',
                    '^': r'\textasciicircum{}', '\n': r'\newline{}'}
    text = unicodedata.normalize('NFC', '' if value is None else str(value))
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    def escape_segment(segment):
        escaped = ''.join(replacements.get(ch, ch) for ch in segment)
        result = []
        for char in escaped:
            if char in _MATH_SYMBOLS:
                result.append(r'\('+_MATH_SYMBOLS[char]+r'\)')
            elif char in _UNICODE_TEXT:
                result.append(_UNICODE_TEXT[char])
            elif ord(char) < 128:
                result.append(char if char.isprintable() else ' ')
            elif (0xC0 <= ord(char) <= 0xFF and unicodedata.category(char).startswith('L')) or char in 'œŒŸ':
                result.append(char)
            elif 0x1D400 <= ord(char) <= 0x1D7FF and unicodedata.normalize('NFKC', char).isascii():
                result.append(unicodedata.normalize('NFKC', char))
            else:
                result.append(r'\texttt{[U+'+format(ord(char), '04X')+']}')
        return ''.join(result)

    marks = {'\u0304': 'overline', '\u0305': 'overline', '\u20d7': 'vec'}
    result, plain = [], []
    i = 0
    while i < len(text):
        if i + 1 < len(text) and text[i + 1] in marks and text[i].isalnum():
            if plain:
                result.append(escape_segment(''.join(plain)))
                plain = []
            command = marks[text[i + 1]]
            result.append(r'\(' + '\\' + command + '{' + escape_segment(text[i]) + r'}\)')
            i += 2
            continue
        plain.append(text[i])
        i += 1
    if plain:
        result.append(escape_segment(''.join(plain)))
    return ''.join(result)

def tex_escape(value):
    """Compatibility name for the shared plain-text conversion."""
    return latex_escape_plain_text(value)


def fmt(value):
    return 'ABS' if value is None else format(value, '.10g').replace('.', ',')


def build_student_data(conn, result, row):
    data = dict(row)
    data['items'] = []
    data['annotations'] = []
    data['conseils'] = []
    data['commentaire_global'] = None
    data['a_verifier'] = []
    data['corrige_latex'] = None
    if row['version_id'] is not None:
        corrige = conn.execute('SELECT str_latex FROM corrige WHERE version_id=?', (row['version_id'],)).fetchone()
        if corrige:
            data['corrige_latex'] = corrige['str_latex']
    if row['correction_id'] is not None:
        cid = row['correction_id']
        data['commentaire_global'] = conn.execute('SELECT commentaire_global FROM correction WHERE id=?', (cid,)).fetchone()[0]
        data['a_verifier'] = [r['texte'] for r in conn.execute('SELECT texte FROM ui_verification WHERE copie_id=? ORDER BY ordre', (row['copie_id'],))]
        data['items'] = [dict(r) for r in conn.execute('''SELECT i.code,i.description,i.bareme_max,
            e.numero exercice,e.titre exercice_titre,q.numero question,q.texte question_texte,ci.points_obtenus,ci.statut,ci.commentaire,ci.annotation
            FROM correction_item ci JOIN item i ON i.id=ci.item_id JOIN question q ON q.id=i.question_id
            JOIN exercice e ON e.id=q.exercice_id WHERE ci.correction_id=? ORDER BY e.ordre,q.ordre,i.ordre,i.id''', (cid,))]
        for table in ('annotations', 'conseils'):
            singular = 'annotation' if table == 'annotations' else 'conseil'
            ordering = 't.page,t.id' if table == 'annotations' else 'COALESCE(t.priorite,999),t.id'
            data[table] = [{k: r[k] for k in r.keys() if k not in {'id', 'correction_id', 'item_id'}} for r in conn.execute(f'''SELECT t.*,i.code item_code FROM {singular} t
                LEFT JOIN item i ON i.id=t.item_id WHERE t.correction_id=? ORDER BY {ordering}''', (cid,))]
    return data


def question_summary(student):
    """Project the detailed marking grid without changing grades or stored items."""
    annotations = {}
    for entry in student.get('annotations', []):
        annotations.setdefault(entry.get('item_code'), []).append(entry.get('texte'))
    questions = {}
    for item in student.get('items', []):
        key = (str(item.get('exercice', '?')), str(item.get('question', '?')))
        row = questions.setdefault(key, {'exercice': key[0], 'question': key[1],
                                        'points': Decimal(0), 'maximum': Decimal(0), 'erreurs': []})
        points = Decimal(0) if student.get('grille_vierge') else Decimal(str(item['points_obtenus']))
        maximum = Decimal(str(item['bareme_max']))
        row['points'] += points
        row['maximum'] += maximum
        if not student.get('grille_vierge') and points < maximum:
            for value in [item.get('commentaire'), item.get('annotation'), *annotations.get(item.get('code'), [])]:
                text = str(value or '').strip()
                if text and text not in row['erreurs']:
                    row['erreurs'].append(text)
    return list(questions.values())


def detailed_grid(student):
    """Three visible levels. Technical codes and correction rules never render."""
    esc = latex_escape_plain_text
    groups = {}
    for item in student.get('items', []):
        groups.setdefault((str(item.get('exercice', '?')), str(item.get('question', '?'))), []).append(item)
    lines = [r'\section*{Grille détaillée}', r'\renewcommand{\arraystretch}{1.15}',
             r'\setlength{\LTpre}{0pt}\setlength{\LTpost}{2pt}',
             r'\begin{longtable}{@{}p{.78\linewidth}>{\centering\arraybackslash}p{.18\linewidth}@{}}']
    previous_ex = None
    for (ex, q), items in groups.items():
        first = items[0]
        if ex != previous_ex:
            title = first.get('exercice_titre') or 'Exercice '+ex
            lines.append(r'\multicolumn{2}{@{}p{.98\linewidth}@{}}{\color{SCblue}\bfseries '+esc(title)+r'}\\*')
        title = first.get('question_texte') or 'Question '+q
        lines.append(r'\textbf{'+esc(title)+r'} & \\*')
        for index, item in enumerate(items):
            row = question_summary(dict(student, items=[item]))[0]
            content = r'\hspace*{3mm}'+esc(item.get('description') or '')
            if row['erreurs']:
                content += r'\newline {\scriptsize\itshape '+esc(' ; '.join(row['erreurs']))+'}'
            points = '' if student.get('grille_vierge') else fmt(float(row['points']))
            lines.append(content+' & '+points+'/'+fmt(float(row['maximum']))+r'\\')
        lines.append(r'\hline')
        previous_ex = ex
    return lines + [r'\end{longtable}']


def render_student(student, subject, cfg):
    """Render the pupil correction stream followed by the reference correction."""
    esc = latex_escape_plain_text
    individual_only = cfg.groupe_mode == 'aucun' or cfg.note_groupe_max == 0
    label = student.get('label') or ('n° '+str(student.get('numero') or '?'))
    if label.startswith('Élève n° '):
        label = label.removeprefix('Élève ')
    if student.get('nom') or student.get('prenom'):
        label = ' '.join(x for x in (student.get('prenom'), student.get('nom')) if x)

    lines = ['% SmartCorrection: paired-a6-v1',
             r'\documentclass[10pt]{article}', r'\usepackage[utf8]{inputenc}',
             r'\usepackage[T1]{fontenc}', r'\usepackage{lmodern,textcomp}', r'\IfFileExists{french.ldf}{\usepackage[french]{babel}}{}', r'\usepackage{amsmath,amssymb,longtable,array}',
             r'\usepackage{xcolor}',
             r'\usepackage[paperwidth=105mm,paperheight=148mm,margin=6mm,bottom=9mm,footskip=4mm]{geometry}',
             r'\definecolor{SCblue}{HTML}{245A81}',
             r'\setlength{\parindent}{0pt}\setlength{\parskip}{3pt}',
             r'\setlength{\tabcolsep}{2.5pt}\setlength{\emergencystretch}{1em}',
             r'\renewcommand{\normalsize}{\fontsize{8.5}{10.5}\selectfont}',
             r'\renewcommand{\small}{\fontsize{7.5}{9}\selectfont}',
             r'\makeatletter',
             r'\renewcommand{\section}{\@startsection{section}{1}{0pt}{6pt}{3pt}{\color{SCblue}\bfseries\normalsize}}',
             r'\renewcommand{\subsection}{\@startsection{subsection}{2}{0pt}{5pt}{2pt}{\color{SCblue}\bfseries\normalsize}}',
             r'\def\SCpanel{Correction}',
             r'\def\@oddfoot{}\let\@evenfoot\@oddfoot\def\@oddhead{}\def\@evenhead{}',
             r'\makeatother',
             r'\pagestyle{empty}',
             r'\begin{document}\normalsize',
             r'\setlength{\abovedisplayskip}{4pt}\setlength{\belowdisplayskip}{4pt}\allowdisplaybreaks']

    title = esc(subject.get('titre') or 'Évaluation')
    lines += [
        r'\begin{tabular}{@{}p{.34\linewidth}p{.39\linewidth}p{.23\linewidth}@{}}',
        r'\textbf{' + title + '} & ' + r'\textbf{' + esc(label) + '} & ' + r'\textbf{' + esc(subject.get('classe') or '') + r'}\\',
        r'\end{tabular}\par',
        r'{\setlength{\fboxsep}{5pt}\setlength{\fboxrule}{.8pt}'
        r'\fcolorbox{SCblue}{white}{\parbox{\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}{\centering\fontsize{14}{17}\selectfont\bfseries ' +
        r'\textbf{' + ('Note provisoire :' if student.get('a_verifier') else 'Note :') + '} ' + ('--' if student.get('note_finale') is None else fmt(student['note_finale'])) + '/' + fmt(cfg.note_finale_max) + r'}}}\par',
    ]
    if not individual_only:
        def score(value):
            return '--' if value is None else fmt(round(value, 2))
        pending = student.get('etat_groupe')
        group_value = 'En attente' if pending and pending.startswith('En attente') else ('À traiter' if pending else score(student.get('note_groupe')))
        final_value = '--' if pending else score(student.get('note_finale'))
        lines += [r'{\scriptsize Individuelle /' + fmt(cfg.note_individuelle_max) + ' : ' + score(student.get('note_individuelle'))
                  + r' \textbullet{} Groupe /' + fmt(cfg.note_groupe_max) + ' : ' + esc(group_value)
                  + r' \textbullet{} Finale /' + fmt(cfg.note_finale_max) + ' : ' + final_value + r'}\par']
    lines += [r'{\color{SCblue}\hrule height .7pt}\vspace{1mm}']

    if student.get('statut') == 'absent':
        lines += [r'\textbf{Absence déclarée.}']
    else:
        if _GRID_MODE.get() == 'detaillee':
            lines += detailed_grid(student)
        else:
            lines += [r'\section*{Bilan par question}',
                      r'\renewcommand{\arraystretch}{1.15}',
                      r'\setlength{\LTpre}{0pt}\setlength{\LTpost}{2pt}',
                      r'\begin{longtable}{@{}>{\raggedright\arraybackslash}p{.20\linewidth}>{\raggedright\arraybackslash}p{.58\linewidth}>{\centering\arraybackslash}p{.18\linewidth}@{}}',
                      r'\small\textcolor{SCblue}{\textbf{Question}} & \small\textcolor{SCblue}{\textbf{Erreurs}} & \small\textcolor{SCblue}{\textbf{Note}}\\\noalign{\hrule height .8pt}\endhead']
            previous_ex = None
            for index, question in enumerate(question_summary(student)):
                if index:
                    lines.append(r'\noalign{\hrule height 1.2pt}' if question['exercice'] != previous_ex else r'\hline')
                label = esc('Ex. '+question['exercice']) + r'\newline ' + esc('Q. '+question['question'])
                errors = r'\newline '.join(esc(error) for error in question['erreurs'])
                # A single longtable row cannot break across pages: keep each question together.
                score = '' if student.get('grille_vierge') else fmt(float(question['points']))
                lines.append(label+' & '+errors+' & '+score+'/'+fmt(float(question['maximum']))+r'\\')
                previous_ex = question['exercice']
            lines += [r'\hline', r'\end{longtable}']

        checks = [str(x).strip() for x in student.get('a_verifier', []) if str(x).strip()]
        if checks:
            lines += [r'{\bfseries\small\textcolor{SCblue}{PROVISOIRE — vérification du professeur nécessaire.}}\par']

        if student.get('commentaire_global'):
            lines += [r'{\scriptsize ' + esc(student['commentaire_global']) + r'}\par']
        if student.get('conseils'):
            advice = [esc(a['texte']) for a in student['conseils'] if a.get('texte')]
            if advice:
                lines += [r'\section*{Conseil}', r'{\scriptsize ' + r' \textbullet{} '.join(advice) + r'}\par']

        checks = [str(x).strip() for x in student.get('a_verifier', []) if str(x).strip()]
        if checks:
            lines += [r'\section*{À vérifier par le prof}',
                      r'\begin{itemize}\setlength{\itemsep}{1pt}\setlength{\parskip}{0pt}']
            lines += [r'\item '+esc(x) for x in checks]
            lines += [r'\end{itemize}']

    lines += [r'\label{sc-correction-end}\clearpage',
              r'\def\SCpanel{Corrigé}\setcounter{page}{1}',
              r'\section*{Corrigé}',
              student.get('corrige_latex') or 'Aucun corrigé enregistré pour cette version.',
              r'\end{document}', '']
    return '\n'.join(lines)

def _sort_text(value):
    text = unicodedata.normalize('NFKD', str(value or '')).casefold()
    return ''.join(c for c in text if not unicodedata.combining(c))


def alphabetical_student_key(student):
    """Identified pupils by surname/given name; anonymous copies come last."""
    anonymous = not (student.get('nom') or student.get('prenom'))
    return (anonymous, _sort_text(student.get('nom')), _sort_text(student.get('prenom')),
            student.get('eleve_id') or 0, student.get('copie_id') or 0)


def render_grade_sheet(students, subject, cfg):
    """Teacher-facing alphabetical grade register for the final document."""
    esc = latex_escape_plain_text
    grouped = cfg.groupe_mode != 'aucun' and cfg.note_groupe_max > 0

    def score(student, key):
        if student.get('statut') == 'absent':
            return 'ABS'
        if student.get('etat_groupe') and key in {'note_groupe', 'note_finale'}:
            return '--'
        value = student.get(key)
        return '--' if value is None else fmt(round(value, 2))

    lines = [r'\documentclass[10pt,a4paper]{article}', r'\usepackage[utf8]{inputenc}',
             r'\usepackage[T1]{fontenc}', r'\usepackage{lmodern,textcomp}',
             r'\IfFileExists{french.ldf}{\usepackage[french]{babel}}{}',
             r'\usepackage{longtable,array,xcolor}', r'\usepackage[margin=15mm]{geometry}',
             r'\definecolor{SCblue}{HTML}{245A81}', r'\setlength{\parindent}{0pt}',
             r'\setlength{\tabcolsep}{4pt}', r'\renewcommand{\arraystretch}{1.25}',
             r'\begin{document}', r'{\Large\bfseries\color{SCblue} Relevé des notes}\par\vspace{1mm}',
             r'{\bfseries '+esc(subject.get('titre') or 'Évaluation')+r'}\hfill '+esc(subject.get('classe') or '')+r'\par\vspace{4mm}']
    if grouped:
        lines += [r'\begin{longtable}{|p{.25\linewidth}|p{.20\linewidth}|>{\centering\arraybackslash}p{.14\linewidth}|>{\centering\arraybackslash}p{.14\linewidth}|>{\centering\arraybackslash}p{.14\linewidth}|}\hline',
                  r'\textcolor{SCblue}{\textbf{Nom}} & \textcolor{SCblue}{\textbf{Prénom}} & '
                  r'\textcolor{SCblue}{\textbf{Indiv. /'+fmt(cfg.note_individuelle_max)+r'}} & '
                  r'\textcolor{SCblue}{\textbf{Groupe /'+fmt(cfg.note_groupe_max)+r'}} & '
                  r'\textcolor{SCblue}{\textbf{Finale /'+fmt(cfg.note_finale_max)+r'}}\\\hline\endhead']
    else:
        lines += [r'\begin{longtable}{|p{.38\linewidth}|p{.38\linewidth}|>{\centering\arraybackslash}p{.16\linewidth}|}\hline',
                  r'\textcolor{SCblue}{\textbf{Nom}} & \textcolor{SCblue}{\textbf{Prénom}} & '
                  r'\textcolor{SCblue}{\textbf{Note /'+fmt(cfg.note_finale_max)+r'}}\\\hline\endhead']
    for student in sorted(students, key=alphabetical_student_key):
        if student.get('nom') or student.get('prenom'):
            surname, given = student.get('nom') or '', student.get('prenom') or ''
        else:
            surname = student.get('label') or f"Copie {student.get('copie_id', '?')}"
            given = 'Non identifié'
        if grouped:
            lines.append(esc(surname)+' & '+esc(given)+' & '+score(student, 'note_individuelle')+' & '+
                         score(student, 'note_groupe')+' & '+score(student, 'note_finale')+r'\\\hline')
        else:
            lines.append(esc(surname)+' & '+esc(given)+' & '+score(student, 'note_finale')+r'\\\hline')
    lines += [r'\end{longtable}', r'\end{document}', '']
    return '\n'.join(lines)


def compile_pdf(tex_path, timeout=60):
    engine = shutil.which('pdflatex')
    if not engine:
        raise RuntimeError('pdflatex introuvable ; installer TeX Live avec le français ou omettre --pdf')
    tex_path = Path(tex_path).resolve()
    paired = tex_path.read_text(encoding='utf-8').startswith('% SmartCorrection: paired-a6-v1\n')
    jobname = tex_path.stem + '.a6' if paired else tex_path.stem
    env = dict(os.environ, openin_any='p', openout_any='p')
    for _ in range(2):
        try:
            run = subprocess.run([engine, '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error', '-jobname='+jobname, tex_path.name],
                                 cwd=tex_path.parent, env=env, capture_output=True, text=False, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f'Compilation trop longue : {tex_path.name}') from exc
        if run.returncode:
            output = (run.stdout or b'').decode('utf-8', errors='replace')
            raise RuntimeError(f'Compilation échouée : {tex_path.name}\n{output[-2500:]}')
    compiled = tex_path.parent/(jobname+'.pdf')
    if not compiled.is_file():
        raise RuntimeError('Aucun PDF produit')
    pdf = tex_path.with_suffix('.pdf')
    if paired:
        aux = (tex_path.parent/(jobname+'.aux')).read_text(encoding='utf-8')
        boundary = re.search(r'\\newlabel\{sc-correction-end\}\{\{\}\{(\d+)\}', aux)
        if not boundary:
            raise RuntimeError('Repère de pagination correction/corrigé absent')
        _pair_a6_pages(compiled, int(boundary.group(1)), pdf)
        _retry_locked(compiled.unlink)
    return pdf


def _pair_a6_pages(pdf_path, left_count, output_path):
    """Keep each stream on its own side, without shrinking or dropping pages."""
    try:
        from pypdf import PdfReader, PdfWriter, Transformation
    except ImportError as exc:
        raise RuntimeError('Installer SmartCorrection avec les dépendances PDF : python -m pip install ".[pdf]"') from exc
    reader = PdfReader(io.BytesIO(Path(pdf_path).read_bytes()))
    if not 0 < left_count < len(reader.pages):
        raise RuntimeError('Pagination correction/corrigé incohérente')
    width, height = 105 * 72 / 25.4, 148 * 72 / 25.4
    for page in reader.pages:
        if abs(float(page.mediabox.width)-width) > .1 or abs(float(page.mediabox.height)-height) > .1:
            raise RuntimeError('Le corrigé a modifié le format A6 attendu')
    writer = PdfWriter()
    try:
        left, right = reader.pages[:left_count], reader.pages[left_count:]
        for i in range(max(len(left), len(right))):
            sheet = writer.add_blank_page(width=2*width, height=height)
            if i < len(left):
                sheet.merge_page(left[i])
            if i < len(right):
                sheet.merge_transformed_page(right[i], Transformation().translate(tx=width))
        writer.add_metadata({'/Title': 'SmartCorrection - Correction et corrigé', '/Creator': 'SmartCorrection / LaTeX'})
        output = io.BytesIO()
        writer.write(output)
        Path(output_path).write_bytes(output.getvalue())
    finally:
        writer.close()


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


def _retry_locked(operation):
    """Give a short-lived file lock time to clear, without hiding lasting failures."""
    for attempt, delay in enumerate((0, .2, .5, 1.0)):
        if delay:
            time.sleep(delay)
        try:
            return operation()
        except PermissionError:
            if attempt == 3:
                raise


def export_results(conn, result, output, pdf=False, combined=False):
    """Build in a fresh directory; never expose partial or stale exports as a success."""
    output = Path(output).resolve()
    if output.exists():
        raise ValueError(f'Le dossier de sortie existe déjà : {output} ; choisir un nouveau dossier')
    cfg = config_from_mapping(result['config'])
    _retry_locked(lambda: output.parent.mkdir(parents=True, exist_ok=True))
    stage = Path(_retry_locked(lambda: tempfile.mkdtemp(prefix='.smartcorrection-', dir=output.parent)))
    try:
        export_grids(conn, result['sujet']['id'], stage)
        students = [build_student_data(conn, result, row) for row in result['notes']]
        payload = dict(result, fiches=students)
        (stage/'notes.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        fields = ['copie_id','eleve_id','numero','statut','groupe','note_brute','bareme_max','note_individuelle','note_groupe','note_finale','camarades','etat_groupe']
        with (stage/'notes.csv').open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fields, delimiter=';')
            writer.writeheader()
            for student in students:
                row = {k: student.get(k) for k in fields}
                row['camarades'] = ' | '.join(f"{p['numero']}: {fmt(p['note_individuelle'])}" for p in student['camarades'])
                writer.writerow(row)
        pdf_paths = []
        for student in students:
            name = f"eleve_{student['numero']:03d}" if student['numero'] is not None else f"copie_{student['copie_id']:04d}"
            path = stage/f"{name}.tex"
            path.write_text(render_student(student, result['sujet'], cfg), encoding='utf-8')
            if pdf:
                pdf_paths.append(compile_pdf(path))
        if pdf and combined:
            from pypdf import PdfWriter
            writer = PdfWriter()
            try:
                for path in sorted(pdf_paths):
                    writer.append(str(path))
                writer.write(str(stage/'corrections.pdf'))
            finally:
                writer.close()
        # Final GUI exports carry copies_exclues. Alongside corrections.pdf, publish
        # a teacher-facing grade register ordered by surname then given name.
        if pdf and 'copies_exclues' in result:
            grade_path = stage/'notes.tex'
            grade_path.write_text(render_grade_sheet(students, result['sujet'], cfg), encoding='utf-8')
            compile_pdf(grade_path)
        manifest = {'format_version': 1, 'sujet_id': result['sujet']['id'], 'pdf': pdf,
                    'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.iterdir()) if p.suffix in {'.json','.csv','.tex','.pdf','.md'} and not p.name.endswith('.a6.pdf')}}
        (stage/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
        for path in stage.iterdir():
            if path.suffix in {'.aux','.log','.out'} or path.name.endswith('.a6.pdf'):
                _retry_locked(path.unlink)
        _retry_locked(lambda: stage.rename(output))
    except Exception as exc:
        try:
            _retry_locked(lambda: shutil.rmtree(stage))
        except OSError as cleanup_error:
            exc.add_note(f'Nettoyage temporaire impossible ({stage}) : {cleanup_error}')
        raise
    return output
