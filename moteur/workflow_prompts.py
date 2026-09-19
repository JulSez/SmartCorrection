"""One instruction per visible action, without concatenated legacy prompts."""
import json
from .correction_contract import describe


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _context(state):
    from .gui_prompts_v2 import _format_line
    d = state['dossier']
    lines = [f"SmartCorrection — {d['titre']} — {d['classe']}", _format_line(state),
             'Travaille avec les documents joints dans cette conversation : sujet, copies, corrigé éventuel et savoir-faire. '
             'Demande un document manquant ; ne prétends pas l’avoir lu.',
             'Les décisions explicites de l’enseignant prévalent. Python calcule les notes : fournis seulement les points par item.']
    if state.get('anonymat', True):
        lines.append('Anonymat actif : utilise C001, C002… ; aucun nom/prénom ni numéro d’élève dans la réponse. identite_lue et numero restent null.')
    else:
        lines.append('Anonymat désactivé : identite_lue peut reprendre le numéro écrit ou le nom/prénom lisible sur la copie. Ne devine rien. numero reste null ; l’affectation est locale.')
    for key in ('generales', 'classe'):
        text = state['consignes'][key].get('texte', '').strip()
        if text:
            lines.append(f'Consignes {key} :\n{text}')
    returns = (state.get('calibrage') or {}).get('retours', '').strip()
    if returns:
        lines.append('Ajustements validés dans ce dossier :\n'+returns)
    return '\n\n'.join(lines)


def _response(example):
    return ('\n\nRÉPONSE : un seul bloc de code json, sans texte autour. Recopie dossier et revision. '
            'Guillemets doubles ; pas de commentaires, NaN ou virgule finale. Échappe les antislashs LaTeX en JSON. '
            'Exemple de forme à adapter à toutes les données demandées :\n```json\n'+compact(example)+'\n```')


def _grid(state):
    fields = ('version', 'exercice', 'question', 'code', 'description', 'bareme_max', 'regle_correction')
    return '\nBARÈME ENREGISTRÉ :\n'+compact([{k: r[k] for k in fields if r.get(k) is not None} for r in state['grille']])


def _marking_rules():
    return ('Chaque item apparaît exactement une fois. Une perte de points exige une erreur courte dans commentaire ou annotation ; '
            'ne répète ni le critère ni le corrigé. La fiche élève regroupe ensuite les items par question : évite donc les commentaires redondants entre items d’une même question. '
            'Une erreur doit tenir en quelques mots. Conseils et annotations sont facultatifs ; un conseil seulement s’il ajoute quelque chose. '
            'Tous ces champs sont du texte brut, pas du LaTeX.\n'
            'Si une copie est impossible à corriger sans deviner : mets-la uniquement dans a_revoir. '
            'a_verifier signale une incertitude non bloquante sur une correction complète.\n'+describe())


def _sample(state, selected):
    version = selected[0]['version'] if selected else state['versions'][0]['version']
    items = [g for g in state['grille'] if g.get('version') in (None, version)]
    return {'reference': selected[0]['reference'] if selected else 'C001',
            'items': [{'item_code': g['code'], 'points_obtenus': 0, 'commentaire': 'Erreur à préciser.'} for g in items],
            'annotations': [], 'conseils': [], 'commentaire_global': None, 'a_verifier': []}


def make_prompt(app, ident, stage, version=None, mode='echantillon'):
    state = app.state(ident)
    d = state['dossier']
    envelope = {'dossier': ident, 'revision': d['revision']}
    context = _context(state)
    if stage == 'bareme':
        example = dict(envelope, versions=[{'version': 'A'}], grilles=[{'nom': 'Barème A', 'version': 'A',
            'exercices': [{'numero': '1', 'questions': [{'numero': '1', 'items': [
                {'code': 'E1Q1I1', 'description': 'Résoudre', 'bareme_max': 2, 'regle_correction': 'Tolérance validée avec l’enseignant'}]}]}]}])
        return context + ('\n\nACTION : discuter et valider le barème. Propose une grille lisible, compacte : '
            'vise 1 ou 2 items par question ; 3 seulement si trois attentes réellement distinctes doivent être notées séparément. '
            'Ne découpe pas artificiellement une même étape en méthode / calcul / rédaction. '
            'Respecte le niveau de rédaction des savoir-faire ; ne crée pas de pénalité non discutée. '
            'Ne rends PAS le JSON avant l’accord de l’enseignant.\n'
            'Après accord : toutes les versions et grilles ; codes uniques par grille et stables ; numéros d’exercice/question en chaînes ; '
            'bareme_max numérique >= 0 ; version:null possible pour une grille commune. Aucun champ validee. '
            'Ne fournis encore ni inventaire des copies ni corrigés.') + _response(example)
    if stage in {'calibrage', 'correction'}:
        if not state['grille'] or not state['versions']:
            raise ValueError('Valider le barème avant de demander une correction')
        calibration = stage == 'calibrage'
        if mode not in {'echantillon', 'reste'}:
            raise ValueError('Mode de correction inconnu')
        if not calibration and mode == 'reste' and not d['echantillon_valide']:
            raise ValueError('Valider le calibrage avant la correction complète')
        selected = [c for c in state['copies'] if c['statut']=='present' and
                    (c['echantillon'] if calibration or mode=='echantillon' else
                     not c['exclue_final'] and (not c['correction_id'] or c['a_revoir']))]
        needs_inventory = not state.get('pretraitement')
        needs_references = any(not v.get('corrige_latex') for v in state['versions'])
        if not selected and (not calibration or not needs_inventory):
            raise ValueError('Aucune copie à corriger dans cette sélection')
        target = compact([{k:c[k] for k in ('reference','version','pages')} for c in selected]) if selected else 'les cinq premières copies du paquet, ou toutes s’il y en a moins'
        action = '\n\nACTION : '+('calibrer la correction' if calibration else 'corriger les copies restantes')+'.\nCopies à traiter : '+target+'.\n'
        example = dict(envelope, corrections=[_sample(state, selected)], a_revoir=[])
        if calibration:
            action += 'Traite exactement le lot : 1 à 5 références au total dans corrections et a_revoir. '
            action += 'moyenne_estimee est une estimation sur 20, jamais une cible de notation ni une raison de durcir le barème.\n'
            example['moyenne_estimee'] = 12.5
            if needs_inventory:
                action += ('Dans CE JSON, pretraitement recense TOUT le paquet : copies avec reference C001…, numero:null, '
                           'identite_lue selon le mode ci-dessus, version et pages physiques >= 1. '
                           'Chaque page est affectée une seule fois ; pages_ignorees contient des objets {"page":3,"motif":"page blanche"}. '
                           'absents:[] : ne déduis aucune absence. Demande les pages/versions incertaines avant de rendre le JSON.\n')
                example['pretraitement'] = {'copies':[{'reference':'C001','numero':None,'identite_lue':None,
                    'version':state['versions'][0]['version'],'pages':[1]}], 'pages_ignorees':[], 'absents':[]}
            else:
                action += 'Inventaire déjà enregistré : ne renvoie pas pretraitement.\n'
            if needs_references:
                action += ('Dans CE JSON, corriges contient TOUTES les versions : '+', '.join(v['version'] for v in state['versions'])+
                    '. Chaque objet contient version et corrige_latex. Corps LaTeX complet, sans documentclass ni begin/end{document}, '
                    'sans accès aux fichiers ni commande externe. Rédaction proche des savoir-faire ; égalités et équivalences alignées '
                    'avec align* ; explications concises sans supprimer les étapes mathématiques.\n')
                example['corriges'] = [{'version':v['version'],'corrige_latex':r'\begin{align*}2x&=4\\x&=2\end{align*}'} for v in state['versions']]
            else:
                action += 'Réutilise les corrigés déjà validés dans cette conversation. Ne renvoie corriges que pour une modification explicitement demandée, avec toutes les versions.\n'
        else:
            action += ('Applique les mêmes décisions à toutes ces copies, y compris celles signalées à reprendre. '
                       'Réutilise les corrigés validés dans cette conversation ; demande-les s’ils manquent. '
                       'Si la réponse est trop longue, envoie plusieurs JSON avec cette enveloppe et des copies complètes, jamais une copie tronquée.\n')
        return context + action + _marking_rules() + _grid(state) + _response(example)
    if stage == 'retour':
        if not d['termine']:
            raise ValueError('Produire le document final avant le retour d’expérience')
        policies = state['consignes']
        example = dict(envelope, base_generale=policies['generales']['id'], base_classe=policies['classe']['id'],
                       generales=policies['generales']['texte'], classe=policies['classe']['texte'])
        # Policies occur only in the example below, rather than twice in this prompt.
        return ('ACTION : préparer les consignes pour la prochaine évaluation. À partir des décisions validées de cette conversation, '
                'réécris deux textes COMPLETS : generales pour toutes les classes, classe pour cette classe. '
                'Conserve les règles encore valables ; ne généralise pas une exception propre à ce sujet. '
                'Aucun nom, numéro d’élève, note individuelle ni code d’item. Présente les changements et attends l’accord de l’enseignant '
                'avant le JSON de remplacement. Recopie les identifiants base_generale/base_classe sans les modifier. '
                'Les textes actuels sont dans l’exemple ; conserve-les s’il n’y a rien à changer.') + _response(example)
    raise ValueError('Étape inconnue')
