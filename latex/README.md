# Fiches LaTeX

`moteur/render.py` construit le document depuis un calcul SQLite effectué dans le même instantané.
Aucun calcul de note n'est délégué à LaTeX. Les fragments de corrigé proviennent de la version
exacte de l'élève. Utiliser `align*` pour aligner les égalités et les équivalences.

La fiche contient : tableau de trois colonnes interro / groupe / finale, notes des camarades en
petit, bilan par item et commentaires, annotations avec page, conseils et corrigé. Le dénominateur
s'adapte à la configuration ; 15 + 5 sur 20 est le défaut. Un absent est explicitement identifié.
Les annotations ne sont pas encore dessinées sur le PDF de la copie originale.

Dépendances : `pdflatex`, classes LaTeX usuelles, AMS, Geometry, Longtable, Latin Modern.
Babel français est utilisé si installé, sinon les textes français restent en UTF-8/T1 sans
césure française. Une distribution TeX Live classique convient. Aucun téléchargement automatique.

La compilation effectue deux passes, sans shell escape, avec un délai de 60 secondes par passe.
Les textes ordinaires sont échappés ; les fragments `str_latex` sont du code LaTeX de confiance,
à relire avant compilation. Ces précautions ne constituent pas un bac à sable complet pour
un fragment LaTeX hostile. Ne pas y inclure de préambule, de lecture externe ni de commande shell.

Les fichiers sont préparés dans un nouveau dossier ; un échec de compilation ne publie pas
un lot incomplet. Choisir un dossier de sortie neuf pour chaque rendu. Les journaux temporaires
sont supprimés après succès, et un extrait d'erreur est affiché après échec.
