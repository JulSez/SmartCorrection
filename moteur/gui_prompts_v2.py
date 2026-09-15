"""Prompts for the compact workflow."""
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


def _privacy_line(state):
    if state.get('anonymat', True):
        return ('MODE ANONYMAT : actif. Ne recopie aucun nom ni prénom d’élève dans les JSON, '
                'commentaires, annotations ou conseils. Utilise uniquement les références C001, C002, etc.\n')
    return ('MODE ANONYMAT : désactivé par l’enseignant. Tu peux lire, conserver dans cette conversation '
            'et restituer les noms/prénoms visibles sur les copies. N’invente jamais une identité illisible.\n')


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
            + _privacy_line(state) +
            'Tu échanges avec l’enseignant dans cette conversation. Les décisions explicites de cette évaluation prévalent. '
            'Les totaux, conversions et éventuelles notes de groupe seront calculés localement par l’application.\n\n')
    if policies:
        text += '\n\n'.join(policies) + '\n\n'
    text += f'Documents à joindre dans cette conversation : {AI_DOCUMENTS}.\n'
    text += 'Ces documents sont joints directement à la conversation IA ; ils ne sont pas téléversés dans SmartCorrection à cette étape.\n'
    text += 'Si un document nécessaire n’est pas joint ou lisible, demande-le à l’enseignant. Ne prétends pas avoir lu un document manquant.\n\n'
    return text, state


def _preprocessing_example(ident, revision, anonymous):
    copy = {'reference': 'C001', 'numero': None, 'version': 'A', 'pages': [1, 2]}
    if not anonymous:
        copy['nom'] = 'DUPONT'
        copy['prenom'] = 'Alice'
    return {
        'dossier': ident,
        'revision': revision,
        'copies': [copy],
        'pages_ignorees': [{'page': 3, 'motif': 'page blanche'}],
        'absents': [],
    }


def make_prompt(app, ident, stage, version=None, mode='echantillon'):
    state = app.state(ident)

    if stage == 'pretraitement':
        prefix, state = _prefix(app, ident)
        d = state['dossier']
        anonymous = state.get('anonymat', True)
        example = _preprocessing_example(ident, d['revision'], anonymous)
        if anonymous:
            identity = ('Utilise des références C001, C002, etc. Ne mets aucun nom, prénom ni numéro d’élève : '
                        'numero doit rester null.')
        else:
            identity = ('Utilise des références C001, C002, etc. Pour chaque copie, recopie le nom et le prénom '
                        'tels qu’ils sont lisibles sur la copie dans les champs nom et prenom. numero reste null. '
                        'Si une identité est partiellement illisible, utilise null uniquement pour la partie illisible et n’invente rien.')
        return prefix + FIXED_JSON_RULES + f'''\nÀ partir du paquet de copies déjà lu dans cette conversation, rends maintenant le prétraitement structuré.
Repère chaque copie, ses pages physiques et sa version probable. {identity} N’invente aucune absence : absents reste vide.

Tu as déjà effectué une première lecture transversale des copies. Conserve dans le contexte de cette conversation une synthèse de travail des erreurs fréquentes, méthodes réellement utilisées, confusions récurrentes et difficultés de rédaction. Cette synthèse ne doit pas apparaître dans le JSON ci-dessous, mais elle devra être réutilisée pour construire ensuite le corrigé de référence et la grille de correction.

Rends uniquement le JSON complet.\nStructure :\n''' + public_json(example)

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

Appuie-toi aussi sur la première lecture transversale des copies effectuée à l’étape 1 : les erreurs communes et méthodes observées doivent t’aider à choisir une rédaction pédagogique claire et à insister sur les points réellement difficiles, sans transformer les erreurs des élèves en règle de correction.

Le champ corrige_latex contient uniquement le corps LaTeX : pas de documentclass, pas de begin/end document, pas de lecture de fichier ni accès externe. Utilise align* ou aligned pour les suites d’égalités et d’équivalences. Le champ sujet_latex est facultatif et peut rester une courte référence au sujet joint ; aucune transcription intégrale n’est requise.

Avant le JSON final, discute avec l’enseignant si une version, une méthode ou une rédaction est ambiguë. Une fois l’accord obtenu, rends seulement le bloc JSON complet. La réponse doit contenir toutes les versions à la fois.
Structure de réponse :\n''' + public_json(example)

    if stage == 'ouverture':
        text = _replace_document_line(legacy_make_prompt(app, ident, stage, version, mode))
        old = ('Le parcours sera : discuter de la grille ; préparer le corrigé LaTeX ; repérer les copies et leurs pages ; '
               'corriger un échantillon de cinq copies maximum ; ajuster avec l’enseignant ; corriger le reste ; '
               'réécrire les consignes réutilisables en fin de travail.')
        new = ('Le parcours sera : choisir la mise en page et valider un gabarit factice ; faire dès maintenant une première lecture et le prétraitement du paquet de copies ; '
               'préparer tous les corrigés de référence ; discuter et valider la grille ; corriger quelques copies ; corriger le lot ; '
               'puis récupérer le document final, le tableau des notes et le retour d’expérience.')
        text = text.replace(old, new)
        text = text.replace('L’enseignant joint le paquet PDF entier, le sujet, une correction si disponible et les cours ou modèles utiles.',
                            'L’enseignant joint directement à cette conversation IA le paquet PDF entier, le sujet, un corrigé s’il existe et les documents de cours de référence utiles.')
        text = text.replace('Pour l’instant, vérifie les documents disponibles, repère les versions du sujet et demande seulement les précisions nécessaires.',
                            'Pour l’instant, vérifie les documents disponibles et repère les versions du sujet. Fais aussi une première lecture transversale du paquet de copies : repère les limites de chaque copie, leurs pages et leur version probable. En parallèle, conserve dans le contexte de cette conversation une synthèse de travail des erreurs communes, méthodes utilisées et difficultés de rédaction observées. Ne produis pas de notes individuelles. Cette synthèse servira ensuite au corrigé de référence et à la grille. Demande seulement les précisions nécessaires.')
        if state.get('anonymat', True):
            privacy = '\nMODE ANONYMAT : actif. Ignore les noms/prénoms visibles sur les copies et n’en restitue aucun.\n'
        else:
            privacy = ('\nMODE ANONYMAT : désactivé par l’enseignant. Lis les noms/prénoms visibles sur les copies et '
                       'conserve-les avec chaque référence Cxxx afin de les restituer dans le résultat de l’initialisation et les étapes de correction. N’invente jamais une identité illisible.\n')
        return _format_line(state) + '\n' + privacy + '\n' + text

    text = legacy_make_prompt(app, ident, stage, version, mode)
    if stage == 'grille':
        versions = [c['version'] for c in state.get('corriges', [])]
        note = ('\n\nLes corrigés de référence ont déjà été validés à l’étape précédente. '
                'Ne les redemande pas et ne change pas leurs versions. Versions à reprendre exactement : '
                + public_json(versions) + '. Le JSON de grille peut conserver le champ versions pour compatibilité, mais il doit reprendre exactement cette liste. '
                'Utilise aussi la première lecture transversale des copies de l’étape 1 pour identifier les erreurs fréquentes et calibrer des critères utiles, sans surpondérer un cas particulier ni inventer une règle non validée par l’enseignant.')
        text += note
    elif stage == 'correction' and not state.get('anonymat', True):
        text = text.replace(
            'Désigne chaque copie uniquement par sa référence C001, etc. Ne recopie aucun nom ni prénom dans les commentaires, annotations ou conseils.',
            'Conserve la référence C001, etc. comme identifiant technique, mais tu peux aussi utiliser le nom/prénom de l’élève dans les commentaires, annotations et conseils puisque l’enseignant a désactivé le mode anonymat.'
        )
        prep = state.get('pretraitement') or {}
        identities = [
            {'reference': c.get('reference'), 'nom': c.get('nom'), 'prenom': c.get('prenom')}
            for c in prep.get('copies', []) if c.get('nom') or c.get('prenom')
        ]
        if identities:
            text += '\n\nIdentités lues sur les copies lors de l’initialisation :\n' + public_json(identities)
    return _format_line(state) + '\n' + _privacy_line(state) + '\n' + text
