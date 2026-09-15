"""Prompts for the compact seven-step GUI workflow."""
from __future__ import annotations

from .gui_prompts import FIXED_JSON_RULES, make_prompt as legacy_make_prompt
from .gui_service import public_json
from .workflow_v2 import format_description

AI_DOCUMENTS = 'copies, sujet, éventuel corrigé et documents de cours de référence'


def _format_line(state):
    layout = state.get('layout')
    if layout:
        c, r = layout['correction'], layout['corrige']
        join = 'côte à côte' if layout['assembly'] == 'cote-a-cote' else 'feuilles séparées'
        target = (f"feuille de correction : {c['pages']} page(s) {c['size']} {c['orientation']} ; "
                  f"corrigé : {r['pages']} page(s) {r['size']} {r['orientation']}, {r['columns']} colonne(s) ; "
                  f"assemblage {join} ; impression terminale {layout['print_format']}.")
    else:
        formats = state.get('formats') or {'correction': 'A6', 'corrige': 'A6'}
        target = (f"feuille de correction {format_description(formats['correction'])} ; "
                  f"corrigé {format_description(formats['corrige'])}.")
    return ('FORMAT CIBLE DU DOCUMENT — à respecter dans la quantité de contenu et la rédaction : '
            + target + ' Ne réduis pas artificiellement la qualité mathématique pour faire tenir le contenu ; '
            'signale plutôt si le format ou le nombre de pages paraît trop petit.')


def _replace_document_line(text):
    marker = 'Documents à joindre dans cette conversation : '
    if marker not in text:
        return text
    before, rest = text.split(marker, 1)
    _old, newline, tail = rest.partition('\n')
    return before + marker + AI_DOCUMENTS + '.' + newline + tail


def _prefix(app, ident):
    state = app.state(ident)
    d = state['dossier']
    policies = []
    for key in ('generales', 'classe'):
        value = state['consignes'][key]
        if value.get('texte'):
            policies.append(f"Consignes {key} :\n{value['texte']}")
    text = (f"SmartCorrection — {d['titre']} — classe {d['classe']}\n"
            f"Dossier : {ident}. Révision de grille : {d['revision']}.\n"
            + _format_line(state) + '\n'
            'Tu échanges avec l’enseignant dans cette conversation. Les décisions explicites de cette évaluation prévalent. '
            'Les totaux, conversions et éventuelles notes de groupe seront calculés localement par l’application.\n\n')
    if policies:
        text += '\n\n'.join(policies) + '\n\n'
    text += f'Documents à joindre dans cette conversation : {AI_DOCUMENTS}.\n'
    text += 'Ces documents sont joints directement à la conversation IA ; ils ne sont pas téléversés dans SmartCorrection à cette étape.\n'
    text += 'Si un document nécessaire n’est pas joint ou lisible, demande-le à l’enseignant. Ne prétends pas avoir lu un document manquant.\n\n'
    return text, state


def make_prompt(app, ident, stage, version=None, mode='echantillon'):
    state = app.state(ident)
    if stage == 'corriges':
        prefix, state = _prefix(app, ident)
        d = state['dossier']
        example = {
            'dossier': ident,
            'revision': d['revision'],
            'corriges': [
                {
                    'version': 'A',
                    'sujet_latex': r'\textit{Sujet joint en PDF.}',
                    'corrige_latex': r'\section*{Exercice 1} ...',
                }
            ],
        }
        return prefix + FIXED_JSON_RULES + '''\nPrépare maintenant TOUS les corrigés de référence de l’évaluation en une seule réponse JSON.
Repère toutes les versions du sujet dans les documents joints. Pour chaque version, fournis un corrigé mathématique complet en LaTeX, proche de la rédaction attendue dans les savoir-faire et modèles de l’enseignant. Si un corrigé est joint, reprends-le fidèlement et signale les incohérences à l’enseignant avant de les modifier.

Le champ corrige_latex contient uniquement le corps LaTeX : pas de documentclass, pas de begin/end document, pas de lecture de fichier ni accès externe. Utilise align* ou aligned pour les suites d’égalités et d’équivalences. Le champ sujet_latex est facultatif et peut rester une courte référence au sujet joint ; aucune transcription intégrale n’est requise.

Avant le JSON final, discute avec l’enseignant si une version, une méthode ou une rédaction est ambiguë. Une fois l’accord obtenu, rends seulement le bloc JSON complet. La réponse doit contenir toutes les versions à la fois.
Structure de réponse :\n''' + public_json(example)

    if stage == 'ouverture':
        text = _replace_document_line(legacy_make_prompt(app, ident, stage, version, mode))
        old = ('Le parcours sera : discuter de la grille ; préparer le corrigé LaTeX ; repérer les copies et leurs pages ; '
               'corriger un échantillon de cinq copies maximum ; ajuster avec l’enseignant ; corriger le reste ; '
               'réécrire les consignes réutilisables en fin de travail.')
        new = ('Le parcours sera : choisir la mise en page et valider un gabarit factice ; commencer dès maintenant le prétraitement du paquet de copies ; '
               'préparer tous les corrigés de référence en une seule fois ; discuter et valider la grille avec un aperçu progressivement rempli ; '
               'importer le prétraitement déjà préparé ; corriger quelques copies ; corriger le lot ; puis récupérer le document final, le tableau des notes et le retour d’expérience.')
        text = text.replace(old, new)
        text = text.replace('L’enseignant joint le paquet PDF entier, le sujet, une correction si disponible et les cours ou modèles utiles.',
                            'L’enseignant joint directement à cette conversation IA le paquet PDF entier, le sujet, un corrigé s’il existe et les documents de cours de référence utiles.')
        text = text.replace('Pour l’instant, vérifie les documents disponibles, repère les versions du sujet et demande seulement les précisions nécessaires.',
                            'Pour l’instant, vérifie les documents disponibles, repère les versions du sujet et commence aussi le prétraitement du paquet : repère les limites de chaque copie, leurs pages et leur version probable. Garde ce repérage dans la conversation ; l’application demandera plus tard le JSON structuré correspondant. Demande seulement les précisions nécessaires.')
        return _format_line(state) + '\n\n' + text

    text = legacy_make_prompt(app, ident, stage, version, mode)
    if stage == 'grille':
        versions = [c['version'] for c in state.get('corriges', [])]
        note = ('\n\nLes corrigés de référence ont déjà été validés à l’étape précédente. '
                'Ne les redemande pas et ne change pas leurs versions. Versions à reprendre exactement : '
                + public_json(versions) + '. Le JSON de grille peut conserver le champ versions pour compatibilité, mais il doit reprendre exactement cette liste.')
        text += note
    return _format_line(state) + '\n\n' + text
