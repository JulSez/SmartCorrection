# Architecture

Le pipeline implémenté suit : JSON d'évaluation + corrections IA structurées → SQLite →
calcul Python → fiches LaTeX, JSON, CSV, Markdown des grilles → compilation PDF optionnelle.
`run` assemble le lot dans une transaction ; `render` recalcule les notes dans le même instantané
que la lecture des détails. Les exports ne dépendent donc pas de caches de notes obsolètes.

La proposition de grille reste une tâche interprétative : sujet, savoir-faire et mémoire de
classe servent d'entrée à l'IA. L'enseignant valide le résultat. Le moteur importe les relations
SQL, puis `prepare-ai` assemble le contexte et le squelette de correction pour une copie.
Aucun appel IA ni lecture automatique d'une conversation n'intervient dans le calcul local.

## Ce qui est normalisé

Sujet → Version → Corrigé ; Sujet → Grille → Exercice → Question → Item ;
Élève → Copie → Correction → CorrectionItem ; Correction → Annotation/Conseil ;
Sujet → Groupe → GroupeEleve. La configuration contient seulement des paramètres, sans
formule arbitraire exécutable. Le modèle et les invariants sont décrits dans `data_model.md`.

## Reproductibilité

Les sommes repartent toujours des points par item. Les grilles utilisées sont figées.
La configuration et les groupes sont relus au recalcul. Les imports d'évaluation identiques
retrouvent leur sujet et les remplacements de correction sont explicites et transactionnels.
Les sorties JSON et LaTeX sont stables à données égales ; les identifiants techniques de lignes
annotation/conseil sont omis des fiches pour rester stables après remplacement. Le manifeste
SHA-256 permet de vérifier le lot exporté. Les PDF peuvent inclure des dates de compilation.

## Suite concrète

Valider le logiciel sur une évaluation réelle fournie par l'enseignant, ajuster les exigences
pédagogiques et le rendu, puis ajouter si utile la superposition des annotations sur les scans.
Les prochains développements doivent partir des données réelles plutôt que d'un nouveau
langage de formules ou d'une infrastructure distante.

## Orchestrateur graphique

`gui.py` fournit un serveur HTTP de bibliothèque standard lié à `127.0.0.1` et sert les fichiers
HTML/CSS/JavaScript de `moteur/web`. `gui_service.py` orchestre imports, révisions et rendus ;
`gui_prompts.py` construit les messages à copier dans ChatGPT depuis les données du dossier.
Aucun fournisseur IA ni service d’hébergement n’est requis.

Les imports graphiques vérifient d’abord l’enveloppe dossier/révision puis réutilisent les
importeurs métier. Une réponse peut ne contenir qu’une partie des copies, mais chaque correction
est complète et la réponse entière est atomique. La commande batch CLI issue de la PR #5 garde
son contrat : exactement toutes les copies présentes du sujet.

`calculate_selection` est réservé à la notation individuelle et peut afficher les copies anonymes
ou un échantillon. Le calcul complet CLI et les groupes gardent leurs validations existantes.
Les deux chemins utilisent les mêmes fonctions pures de calcul et les mêmes tables de scores.
Les fiches sortent par le même rendu LaTeX ; pypdf assemble le document collectif.

La mémoire pédagogique du parcours graphique est dans SQLite. ChatGPT propose deux textes de
remplacement en fin de correction ; l’enseignant relit les différences avant validation. Les
dossiers futurs utilisent les nouvelles consignes et les dossiers en cours conservent leur
instantané. [Détails et contrats](interface.md).
