# Fiches LaTeX

`moteur/render.py` construit le document depuis un calcul SQLite effectué dans le même instantané.
Aucun calcul de note n'est délégué à LaTeX. Les fragments de corrigé proviennent de la version
exacte de l'élève. Utiliser `align*` pour aligner les égalités et les équivalences.

La fiche finale est une **A5 paysage (210 × 148 mm)** composée de deux zones **A6 portrait
(105 × 148 mm)**. Les titres et filets sont bleus, les en-têtes de tableaux bleu clair.

- À gauche : sujet, version, classe, identité locale de l'élève (ou référence anonyme),
  note dans un tableau d'une ligne et deux colonnes, puis tableau **Question / Description du
  critère / Note / Retour**, annotations avec page et conseils.
- À droite : corrigé intégral de la version, avec ses formules et alignements LaTeX.

La note finale et son dénominateur viennent du calcul Python. En mode groupe, le détail
interro / groupe et les notes des camarades restent affichés sous la note finale. Une absence
est explicitement identifiée. Aucune règle de calcul ni décision pédagogique n'est modifiée.
Les annotations ne sont pas encore dessinées sur le PDF de la copie originale.

Dépendances : `pdflatex`, classes LaTeX usuelles, AMS, Geometry, Longtable, xcolor/colortbl,
Latin Modern, et `pypdf` (`python -m pip install ".[pdf]"`, déjà inclus dans `.[gui]`).
Babel français est utilisé si installé, sinon les textes français restent en UTF-8/T1 sans
césure française. Une distribution TeX Live classique convient. Aucun téléchargement automatique.

La compilation effectue deux passes, sans shell escape, avec un délai de 60 secondes par passe.
LaTeX compose d'abord deux suites de pages A6 indépendantes dans le même fichier : correction,
puis corrigé. Un repère dans le `.aux` indique leur séparation ; `compile_pdf` les place ensuite
côte à côte sur les feuilles A5 avec `pypdf`, sans réduire ni rasteriser le texte. Si un côté
dépasse, il continue du même côté sur la feuille suivante ; le côté terminé reste blanc.
Il n'y a pas de limite à une feuille et le corrigé n'est pas tronqué pour tenir en A6.
Les tableaux répètent leur en-tête en cas de saut de page. Un bloc LaTeX indivisible trop haut
(par exemple une immense `minipage`) ou une formule trop large doit être repris dans le corrigé.

Les `.tex` exportés contiennent les deux flux complets. Une compilation directe par `pdflatex`
donne les pages A6 successives ; passer par l'application, `smartcorrection render --pdf` ou
`moteur.render.compile_pdf` pour obtenir les feuilles A5 assemblées.
Les textes ordinaires sont échappés ; les fragments `str_latex` sont du code LaTeX de confiance,
à relire avant compilation. Ces précautions ne constituent pas un bac à sable complet pour
un fragment LaTeX hostile. Ne pas y inclure de préambule, de lecture externe ni de commande shell.

Tous les champs de texte libre passent par `latex_escape_plain_text` : titres, classe, élève,
questions, descriptions, commentaires, commentaire global, annotations et conseils. La fonction
échappe d'abord les caractères réservés (`&`, `%`, `$`, `_`, accolades, antislash, etc.), puis
convertit les symboles Unicode courants en équivalents compatibles avec `pdflatex` : notamment
`−`, `×`, `√`, `≤`, `≥`, `≠`, flèches, infini, ensembles, lettres grecques et indices/exposants.
Les accents français restent lisibles et les espaces typographiques sont normalisés.
Un caractère sans équivalent connu est affiché sous la forme `[U+XXXX]`, au lieu de faire
échouer toute la compilation ; le texte original reste intact dans SQLite et les exports JSON.
Cette conversion ne s'applique jamais au fragment `corrige_latex`, dont les commandes et
environnements mathématiques sont conservés intégralement.

Les fichiers sont préparés dans un nouveau dossier ; un échec de compilation ne publie pas
un lot incomplet. Choisir un dossier de sortie neuf pour chaque rendu. Les journaux temporaires
sont supprimés après succès, et un extrait d'erreur est affiché après échec.


Dans l’interface, chaque génération utilise un nouveau dossier local. Les PDF individuels sont
assemblés par `pypdf` en `corrections.pdf`, ouvert depuis l’écran. Les anciennes sorties restent
consultables et sont signalées « à régénérer » dès que leurs données ont changé.
