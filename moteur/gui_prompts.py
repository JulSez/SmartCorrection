"""Self-contained copy/paste instructions. No remote API call or hidden chat dependency."""
import json
from .db import database
from .gui_service import _policy, public_json


FIXED_JSON_RULES = '''BLOC TECHNIQUE FIXE — À RESPECTER EXACTEMENT
Tu dois distinguer la discussion pédagogique du rendu machine. Quand cette étape demande du JSON :
- rends un unique bloc de code ```json contenant un objet JSON valide, fermé par ``` ; ce bloc doit permettre à l’enseignant d’utiliser le bouton Copier ;
- aucun texte avant ou après le bloc de code, aucun tableau ni autre mise en forme Markdown dans le rendu final ;
- utilise des guillemets doubles, aucune virgule finale, aucun commentaire, aucune valeur NaN ou Infinity ;
- respecte exactement les noms de champs, les types et la structure de l’exemple ; n’ajoute aucun champ ;
- recopie exactement l’enveloppe dossier et revision fournie par l’application ;
- les nombres sont des nombres JSON, les identifiants et numéros sont des chaînes ou des entiers selon l’exemple ;
- ne calcule ni note brute, ni note finale, ni moyenne : Python s’en charge ;
- si une donnée nécessaire est illisible ou inconnue, utilise null seulement quand l’exemple l’autorise ou signale la copie dans a_revoir ; n’invente jamais.
L’application valide le JSON avant tout enregistrement. Une réponse non conforme sera refusée et devra être corrigée en conservant les décisions pédagogiques déjà prises.
'''

FIXED_LATEX_RULES = '''BLOC TECHNIQUE FIXE — RENDU LATEX
Rends uniquement le corps LaTeX demandé dans un unique bloc de code ```latex, fermé par ```, avec le bouton Copier. Aucun texte autour du bloc, aucun tableau ni autre mise en forme Markdown. Le code est sans \\documentclass, sans \\begin{document} et sans \\end{document}.
N’inclus aucune commande de lecture de fichier, aucun script, aucun accès externe et aucun calcul de note. Les formules doivent être du LaTeX compilable ; utilise align* ou aligned pour aligner les égalités et les équivalences.
'''


def fixed_contract(stage):
    return FIXED_LATEX_RULES if stage == 'corrige' else FIXED_JSON_RULES


def make_prompt(app, ident, stage, version=None, mode='echantillon'):
    state=app.state(ident)
    d=state['dossier']
    with database(app.db_path) as conn:
        policies=[]
        for rid in (d['generale_id'],d['classe_id']):
            if rid:
                r=conn.execute('SELECT portee,texte FROM consigne_revision WHERE id=?',(rid,)).fetchone()
                policies.append(f"Consignes {r['portee']} :\n{r['texte']}")
        previous_grid=conn.execute("SELECT texte FROM ui_echange WHERE dossier_id=? AND etape='grille' ORDER BY id DESC LIMIT 1",(ident,)).fetchone()
    prefix=f"SmartCorrection — {d['titre']} — classe {d['classe']}\nDossier : {ident}. Révision de grille : {d['revision']}.\n"
    prefix+='Tu échanges avec l’enseignant dans cette conversation. Les décisions explicites de cette évaluation prévalent. La notation de ce parcours est individuelle, sans groupe. Les calculs de totaux et la conversion sur 20 seront faits par l’application.\n\n'
    prefix+='\n\n'.join(policies)+'\n\n'
    # Never include the class roster, pupil numbers or uploaded filenames in prompts.
    # Filenames may themselves contain pupils' names; document roles are sufficient.
    prefix+='Documents à joindre dans cette conversation : '+', '.join(dict.fromkeys(f['role'] for f in state['fichiers']))+'.\n'
    prefix+='Si un document nécessaire n’est pas joint ou lisible, demande-le à l’enseignant. Ne prétends pas avoir lu un document manquant.\n\n'
    prefix += fixed_contract(stage) + '\n'
    envelope={'dossier':ident,'revision':d['revision']}
    if stage=='ouverture':
        return prefix+'''Nous allons préparer et corriger un paquet de copies de mathématiques.
L’enseignant joint le paquet PDF entier, le sujet, une correction si disponible et les cours ou modèles utiles.
Le parcours sera : discuter de la grille ; préparer le corrigé LaTeX ; repérer les copies et leurs pages ; corriger un échantillon de cinq copies maximum ; ajuster avec l’enseignant ; corriger le reste ; réécrire les consignes réutilisables en fin de travail.
Attends les consignes de chaque étape fournies par l’application. Pour l’instant, vérifie les documents disponibles, repère les versions du sujet et demande seulement les précisions nécessaires.
La pagination désigne les pages physiques du PDF source, à partir de 1. Le paquet n’a pas besoin d’être découpé.
'''
    if stage=='grille':
        example=dict(envelope,versions=[{'version':'A'}],grilles=[{'nom':'Grille A','version':'A','exercices':[{'numero':'1','titre':'Exercice 1','questions':[{'numero':'1','texte':'Question du sujet','items':[{'code':'E1Q1I1','description':'Critère à préciser','bareme_max':1,'regle_correction':'Règle discutée avec l’enseignant'}]}]}]}])
        text='Discute avec l’enseignant d’une grille de notation détaillée à partir du sujet, du cours, des modèles et des consignes. Présente d’abord une grille lisible. Ajuste critères, points, rédaction attendue et tolérances. Ne transforme pas une hypothèse en règle validée.\n'
        text+='Après accord de l’enseignant, rends le JSON complet au format ci-dessous dans un unique bloc de code json, sans texte autour. Inclure toutes les versions et tous les items ; les codes sont stables et uniques dans leur grille. Les numéros d’exercice/question sont des chaînes, les points des nombres positifs ou nuls. Une grille peut être commune (version:null). Ne fournis pas de champ validee : l’enseignant valide dans l’application. Le sujet_latex dans chaque version est facultatif ; aucune transcription intégrale du sujet n’est exigée.\n'
        if previous_grid:
            text+='Grille précédemment enregistrée, à ajuster si nécessaire :\n'+previous_grid['texte']+'\n'
        return prefix+text+'Structure de réponse (exemple à remplacer et développer) :\n'+public_json(example)
    if stage=='corrige':
        if version not in [v['version'] for v in state['versions']]:
            raise ValueError('Choisir une version du sujet')
        text=f'Prépare le corrigé mathématique complet de la version {version}, en suivant la rédaction des savoir-faire. Si un corrigé est joint, reprends-le fidèlement et signale à l’enseignant les incohérences éventuelles avant de les modifier. Vérifie la cohérence avec les critères ci-dessous.\n'
        text+='Discute les points nécessaires, puis rends le corps LaTeX complet dans un unique bloc de code latex, sans texte autour, sans documentclass ni begin/end document. L’application utilise article, amsmath, amssymb, longtable, array, geometry et lmodern. Aligne les égalités et les équivalences avec align* ou aligned. Ne résume pas le corrigé pour le faire tenir sur une page : développe toutes les questions et laisse LaTeX répartir le contenu sur plusieurs pages. Évite les blocs non sécables englobant tout le corrigé. N’ajoute aucune commande de lecture de fichier, de script ou d’accès externe. N’effectue aucun calcul de note dans LaTeX.\n'
        return prefix+text+'Grille enregistrée :\n'+public_json(state['grille'])
    if stage=='copies':
        packet=next((f for f in state['fichiers'] if f['role']=='paquet'),None)
        if not packet:
            raise ValueError('Ajouter le paquet PDF')
        example=dict(envelope,copies=[{'reference':'C001','numero':None,'version':state['versions'][0]['version'] if state['versions'] else 'A','pages':[1]}],pages_ignorees=[],absents=[])
        return prefix+f'''Repère les copies dans le paquet de {packet['pages']} pages. Une copie peut occuper plusieurs pages, y compris non contiguës. Utilise les pages physiques du PDF source, la première étant 1.
Attribue une référence stable C001, C002, etc., en t’appuyant uniquement sur le PDF. La liste des élèves n’est pas transmise. Garde numero:null pour chaque copie : l’association à un élève se fera localement dans l’application. Ne recopie aucun nom ni prénom dans le JSON. Une identité inconnue n’empêche pas de traiter la copie. Repère la version ; demande à l’enseignant si elle est incertaine.
Toutes les pages doivent être affectées exactement une fois à une copie ou à pages_ignorees (avec page et motif, par exemple page blanche). Ne déduis pas une absence d’une identité non retrouvée. Laisse absents vide ; seul l’enseignant peut déclarer une absence localement.
Après discussion, rends le JSON complet dans un unique bloc de code json, sans texte autour. Les numéros et les pages sont des entiers. Ne donne aucun chemin de fichier ni identifiant SQLite.
'''+ '\nVersions : '+public_json([v['version'] for v in state['versions']])+'\nStructure :\n'+public_json(example)
    if stage=='correction':
        if mode not in {'echantillon','reste'}:
            raise ValueError('Mode de correction inconnu')
        if mode=='reste' and not d['echantillon_valide']:
            raise ValueError('Valider l’échantillon avant de corriger le reste')
        selected=[c for c in state['copies'] if c['statut']=='present' and
                  (c['echantillon'] if mode=='echantillon' else (not c['correction_id'] or c['a_revoir']))]
        if not selected:
            raise ValueError('Aucune copie à corriger dans cette sélection')
        public_copies=[{k:c[k] for k in ('reference','version','pages')} for c in selected]
        template=dict(envelope,corrections=[{'reference':selected[0]['reference'],'items':[{'item_code':'CODE_DE_LA_GRILLE','points_obtenus':None,'statut':None,'commentaire':None,'annotation':None}],'annotations':[],'conseils':[],'commentaire_global':None}],a_revoir=[])
        text='Corrige les copies de la sélection ci-dessous avec la grille et le corrigé fournis. Chaque item reçoit exactement un score entre 0 et son maximum. Quand le maximum n’est pas attribué, fournir un commentaire ou une annotation expliquant précisément les points perdus. Le statut, facultatif, est acquis, partiel, non_acquis ou non_repondu.\n'
        text+='Désigne chaque copie uniquement par sa référence C001, etc. Ne recopie aucun nom ni prénom dans les commentaires, annotations ou conseils.\n'
        text+='Propose des conseils concrets pour chaque copie. Les conseils ont texte, item_code facultatif et priorite entière facultative. Une annotation localisée a item_code, page, texte ; x/y et largeur/hauteur, facultatifs, sont des fractions de page entre 0 et 1, origine en haut à gauche. Utilise uniquement les pages de cette copie dans le PDF source.\n'
        text+='Ne confonds pas absence de réponse et écriture illisible. Si une copie ne peut être corrigée complètement sans deviner, ne donne pas de correction pour elle ; ajoute {"reference":"C001","motif":"..."} dans a_revoir. Les points null ne sont pas importables.\n'
        text+='Rends le JSON complet dans un unique bloc de code json avec dossier/revision, corrections et a_revoir, sans texte autour. Aucune note brute, finale, moyenne ou note de groupe. Si la réponse est trop longue, tu peux rendre plusieurs messages contenant chacun un bloc json avec des copies complètes et la même enveloppe. L’enseignant peut les importer successivement ; l’application indique les copies encore à traiter. Ne tronque jamais une copie pour raccourcir la réponse.\n'
        text+='Après les remarques de l’enseignant, fournis de nouveau les corrections complètes des seules copies modifiées. Conserve leurs références et les codes des items.\n'
        return prefix+text+'Sélection :\n'+public_json(public_copies)+'\nGrille :\n'+public_json(state['grille'])+'\nCorrigés :\n'+public_json([{'version':v['version'],'latex':v['corrige_latex']} for v in state['versions']])+'\nStructure :\n'+public_json(template)
    if stage=='retour':
        if not d['termine']:
            raise ValueError('Produire le document final avant le retour d’expérience')
        general=state['consignes']['generales'];classe=state['consignes']['classe']
        example=dict(envelope,base_generale=general['id'],base_classe=classe['id'],generales=general['texte'],classe=classe['texte'])
        return prefix+'''Nous avons terminé la correction. À partir de la discussion avec l’enseignant, réécris les consignes destinées aux prochaines évaluations.
Fournis deux textes COMPLETS de remplacement :
- generales : principes de correction réutilisables dans toutes les classes ;
- classe : attentes, rédaction, tolérances et adaptations propres à cette classe.
Intègre les décisions effectivement prises avec l’enseignant. Conserve les consignes précédentes encore valables. N’invente pas de règle issue d’un exemple ou d’un comportement par défaut du logiciel. Ne conserve ni notes individuelles, ni noms/numéros d’élèves, ni références à un item ponctuel. Les règles limitées à cette seule évaluation restent dans sa grille.
Présente les changements à l’enseignant avant le JSON final. Les textes vont remplacer les consignes actives après sa validation dans l’application ; ils ne seront pas ajoutés à la suite des anciens textes. S’il n’y a pas de changement, conserve le texte actuel.
Recopie exactement dossier, revision, base_generale et base_classe. Rends le JSON final dans un unique bloc de code json, sans texte autour. Les champs generales et classe sont des chaînes de texte, pas des listes ni des objets.
Consignes actuelles et enveloppe à compléter :
'''+public_json(example)
    raise ValueError('Étape inconnue')
