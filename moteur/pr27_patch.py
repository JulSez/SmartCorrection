"""PR27: two-part student correction sheet, hierarchical grid, optional page break."""
from __future__ import annotations

from contextvars import ContextVar

from . import render
from . import workflow_v2 as workflow
from . import pr17_patch as pr17
from . import pr18_patch as pr18
from . import pr25_patch as previous
from .db import database

WorkflowApplication = previous.WorkflowApplication
_BASE_RENDER_STUDENT = render.render_student
_BASE_GENERATE = WorkflowApplication.generate
_BASE_APPLY_SOURCE_LAYOUT = pr18._apply_source_layout
_ACTIVE_LAYOUT = ContextVar('smartcorrection_pr27_layout', default=None)

# New dossiers expose the page-break option. Existing saved layouts inherit it
# without a migration because pr18 merges saved values onto this default.
pr18._DEFAULT_LAYOUT['correction']['newpage_after_correction'] = True


def _layout_summary(layout):
    text = pr18._layout_summary_original(layout)
    enabled = layout.get('correction', {}).get('newpage_after_correction', True)
    return text + (' Saut de page après correction : oui.' if enabled else ' Saut de page après correction : non.')


def _feedback_lines(student, esc):
    lines = []
    if student.get('commentaire_global'):
        lines.append(esc(student['commentaire_global']))
    detailed = []
    for item in student.get('items', []):
        feedback = [item.get('commentaire'), item.get('annotation')]
        feedback = [x for x in feedback if x]
        if feedback:
            label = f"Ex. {item.get('exercice', '?')} — Q. {item.get('question', '?')}"
            detailed.append(r'\item \textbf{' + esc(label) + '} — ' + esc(' '.join(feedback)))
    for annotation in student.get('annotations', []):
        text = annotation.get('texte')
        if text:
            page = annotation.get('page')
            prefix = f"Page {page} — " if page is not None else ''
            detailed.append(r'\item ' + esc(prefix + text))
    if detailed:
        lines += [r'\begin{itemize}\setlength{\itemsep}{1pt}\setlength{\parskip}{0pt}'] + detailed + [r'\end{itemize}']
    return lines


def _grid_lines(student, esc):
    lines = [r'\section*{Grille}',
             r'\renewcommand{\arraystretch}{1.14}',
             r'\setlength{\LTpre}{0pt}\setlength{\LTpost}{3pt}',
             r'\begin{longtable}{@{}>{\raggedright\arraybackslash}p{.20\linewidth}>{\raggedright\arraybackslash}p{.58\linewidth}>{\centering\arraybackslash}p{.18\linewidth}@{}}',
             r'\small\textcolor{SCblue}{\textbf{Question}} & \small\textcolor{SCblue}{\textbf{Critère}} & \small\textcolor{SCblue}{\textbf{Note}}\\\noalign{\hrule height .8pt}\endhead']
    previous_ex = previous_q = None
    for index, item in enumerate(student.get('items', [])):
        ex = str(item.get('exercice', '?'))
        q = str(item.get('question', '?'))
        if index:
            if ex != previous_ex:
                lines.append(r'\noalign{\hrule height 1.2pt}')
            elif q != previous_q:
                lines.append(r'\hline')
            else:
                lines.append(r'\multicolumn{3}{@{}l@{}}{\makebox[\linewidth]{\color{black!32}\dotfill}}\\[-5pt]')
        question = esc('Ex. ' + ex) + r'\newline ' + esc('Q. ' + q)
        lines.append(question + ' & ' + esc(item.get('description') or '') + ' & ' +
                     render.fmt(item.get('points_obtenus')) + '/' + render.fmt(item.get('bareme_max')) + r'\\')
        previous_ex, previous_q = ex, q
    lines += [r'\hline', r'\end{longtable}']
    return lines


def _verification_lines(student, esc):
    checks = student.get('a_verifier') or []
    if isinstance(checks, str):
        checks = [checks]
    reason = student.get('a_revoir')
    if reason and reason not in checks:
        checks = list(checks) + [reason]
    checks = [str(x).strip() for x in checks if str(x).strip()]
    if not checks:
        return []
    return [r'\section*{À vérifier par le prof}',
            r'\begin{itemize}\setlength{\itemsep}{1pt}\setlength{\parskip}{0pt}'] + \
           [r'\item ' + esc(x) for x in checks] + [r'\end{itemize}']


def _compact_header(student, subject, cfg, esc):
    title = esc(subject.get('titre') or 'Évaluation')
    if student.get('nom') or student.get('prenom'):
        name = ' '.join(x for x in (student.get('prenom'), student.get('nom')) if x)
    else:
        name = student.get('label') or ('n° ' + str(student.get('numero') or '?'))
    note = '--' if student.get('note_finale') is None else render.fmt(student['note_finale'])
    return [r'\begin{tabular}{@{}p{.34\linewidth}p{.39\linewidth}p{.23\linewidth}@{}}',
            r'\textbf{' + title + '} & ' + r'\textbf{' + esc(name) + '} & ' + r'\textbf{' + esc(subject.get('classe') or '') + r'}\\',
            r'\end{tabular}\par',
            r'\textbf{Note :} ' + note + '/' + render.fmt(cfg.note_finale_max) + r'\par',
            r'{\color{SCblue}\hrule height .7pt}\vspace{1mm}']


def _compact_corrige(source, student, subject, esc):
    old = '\n'.join([
        r'\def\SCpanel{Corrigé}\setcounter{page}{1}',
        r'\SCtitle{Corrigé}',
        r'{\bfseries ' + esc(subject.get('titre') or 'Évaluation') + r'}\par',
        r'\textbf{Version :} ' + esc(student.get('version') or '?') + r'\hfill\textbf{Classe :} ' + esc(subject.get('classe') or '') + r'\par\vspace{2mm}',
    ])
    new = '\n'.join([
        r'\def\SCpanel{Corrigé}\setcounter{page}{1}',
        r'{\bfseries\color{SCblue} Corrigé}\par\vspace{2mm}',
    ])
    return source.replace(old, new, 1)


def _render_student(student, subject, cfg):
    source = _BASE_RENDER_STUDENT(student, subject, cfg)
    esc = render.latex_escape_plain_text
    start = source.find(r'\SCtitle{Correction}')
    body_start = source.find(r'\section*{Correction}', start)
    end = source.find(r'\label{sc-correction-end}', body_start)
    if start == -1 or body_start == -1 or end == -1:
        return _compact_corrige(source, student, subject, esc)

    head = source[:start]
    body = _compact_header(student, subject, cfg, esc)
    if student.get('statut') == 'absent':
        body += [r'\section*{Correction}', r'\textbf{Absence déclarée.}']
    else:
        body += [r'\section*{Correction}'] + _feedback_lines(student, esc)
        body += [r'% SC:after-correction', r'\section*{Conseils}']
        if student.get('conseils'):
            body += [r'\begin{itemize}\setlength{\itemsep}{1pt}\setlength{\parskip}{0pt}']
            body += [r'\item ' + esc(item.get('texte') or '') for item in student['conseils'] if item.get('texte')]
            body += [r'\end{itemize}']
        body += _grid_lines(student, esc)
        body += _verification_lines(student, esc)

    tail = source[end:]
    rebuilt = head + '\n'.join(body) + '\n' + tail
    rebuilt = _compact_corrige(rebuilt, student, subject, esc)
    active = _ACTIVE_LAYOUT.get()
    if active is not None:
        rebuilt = _apply_page_break(rebuilt, active)
    return rebuilt


def _apply_page_break(source, layout):
    enabled = layout.get('correction', {}).get('newpage_after_correction', True)
    return source.replace(r'% SC:after-correction', r'\newpage' if enabled else '', 1)


def _apply_source_layout(source, layout):
    source = _BASE_APPLY_SOURCE_LAYOUT(source, layout)
    return _apply_page_break(source, layout)


def _generate(self, ident, final=False, pdf=True):
    with database(self.db_path) as conn:
        layout = pr18._layout(conn, ident)
    token = _ACTIVE_LAYOUT.set(layout)
    try:
        return _BASE_GENERATE(self, ident, final=final, pdf=pdf)
    finally:
        _ACTIVE_LAYOUT.reset(token)


# Preserve PR26's wrapped layout behavior, then add the correction-page option.
if not hasattr(pr18, '_layout_summary_original'):
    pr18._layout_summary_original = pr18._layout_summary
pr18._layout_summary = _layout_summary
pr18._apply_source_layout = _apply_source_layout
# PR17 temporarily swaps in compact_corrige_source during final generation. Point
# that hook at the new renderer so the student-sheet redesign is not bypassed.
pr17.compact_corrige_source = _render_student
render.render_student = _render_student
workflow.render_student = _render_student
WorkflowApplication.generate = _generate
