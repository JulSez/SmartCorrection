# SmartCorrection

Moteur **local**, Python 3.11+ et SQLite, sans dépendance Python externe ni appel IA
pour les imports, les calculs ou les exports. L'IA propose le barème et interprète les copies ;
l'enseignant valide la grille, et Python calcule les notes à partir de chaque item.

## Premier pipeline complet

Depuis la racine du dépôt :

```sh
python -m unittest discover -s tests -v
python -m moteur run examples/tmex_demo/pipeline.json --db db/demo.sqlite --output exports/demo
```

Produit `notes.json`, `notes.csv`, un `.tex` par élève, les grilles en Markdown et un manifeste SHA-256 des sorties.
Pour compiler aussi les PDF, ajouter `--pdf` (TeX Live : LaTeX, AMS, Latin Modern,
Geometry, Longtable ; français recommandé). Le français est utilisé si `french.ldf` est installé.
Pour une installation Python : `python -m pip install .`, puis la commande `smartcorrection`
est disponible hors du dépôt ; le schéma SQL est inclus dans le paquet.

La démo est **fictive**, explicitement étiquetée, avec les numéros 2, 31, 3 et 22,
deux versions /15 et /30 et une absence. Résultats finaux attendus : 16 ; 18,5 ; 13,5 ; ABS.
Aucune évaluation réelle ni copie source n'était présente dans le dépôt initial.

Un import identique d'évaluation retrouve le même sujet. Les corrections existantes demandent
`--replace`. Les sorties exigent un nouveau dossier, pour éviter un mélange avec un ancien rendu :

```sh
python -m moteur run examples/tmex_demo/pipeline.json --db db/demo.sqlite --output exports/demo-v2 --replace --pdf
```

## Importer une classe depuis un CSV

Une liste de classe peut rester entièrement locale. Placer par exemple le fichier dans `private/`
(ce dossier est ignoré par Git), avec les colonnes `nom,prenom` :

```csv
nom,prenom
DUPONT,Alice
MARTIN,Léo
```

Puis importer la classe :

```sh
smartcorrection import-classe private/1GSpe.csv --classe "1GSpé" --db db/1gspe.sqlite
```

Les séparateurs virgule, point-virgule et tabulation sont acceptés, ainsi que les en-têtes avec
accents (`Prénom`). Si la colonne `numero` est absente, l'ordre des lignes du CSV attribue les
numéros 1, 2, 3, etc. Une colonne `numero` peut être fournie pour imposer des numéros stables.
Un nouvel import identique est idempotent ; un nom différent pour un numéro déjà utilisé est
refusé sans modification partielle.

Une évaluation de la même classe peut ensuite référencer directement ces numéros dans `copies`
ou `groupes`, sans recopier les noms dans `evaluation.json`.

## Associer un gros PDF de copies sans le découper

SmartCorrection peut conserver **un seul PDF source pour toute l'évaluation**. Chaque copie
logique reste rattachée à un élève, mais ne crée aucun fichier PDF individuel : elle référence
simplement une ou plusieurs pages du PDF source.

Exemple `private/copies.csv` :

```csv
numero;version;pages;statut
1;A;1;present
2;B;2;present
3;A;3-4;present
4;B;;absent
```

Puis :

```sh
smartcorrection import-copies private/copies.csv --sujet 1 --pdf private/copies.pdf --db db/1gspe.sqlite
```

`pages` accepte un numéro, une plage (`3-5`) ou plusieurs valeurs (`1,3-5`, à citer si le CSV
utilise la virgule comme séparateur). Une même page d'un même PDF ne peut pas être affectée à
deux copies. Un nouvel import identique est idempotent. Avant correction, `--replace` permet de
corriger une association ; après correction, l'identité de la copie, le PDF et ses pages sont figés.

`prepare-ai` renvoie ensuite `source.pdf_path` et `source.pages`. Pour une copie issue d'un PDF
partagé, les annotations utilisent les numéros de page du PDF source.

## Utilisation sur une vraie évaluation

1. Importer la classe depuis un CSV local, puis préparer `classes/<classe>.md`, les savoir-faire
   et le JSON d'évaluation suivant [le contrat](docs/evaluation_format.md). Le JSON peut ne contenir
   encore aucune copie.
2. Relire la grille ; inscrire `validee: true` seulement après cette revue, ou la valider en CLI.
3. Importer l'évaluation, puis associer les élèves aux pages du PDF source :

```sh
python -m moteur import-evaluation evaluation.json --db db/classe.sqlite
python -m moteur import-copies private/copies.csv --sujet 1 --pdf private/copies.pdf --db db/classe.sqlite
python -m moteur validate-grid --db db/classe.sqlite --grille 1
```

4. Préparer le contexte à transmettre à l'IA :

```sh
python -m moteur prepare-ai --db db/classe.sqlite --copie 1 --classe-md classes/TMEX.md --savoir-faire savoir-faire/equations.md > contexte.json
```

Fournir à l'IA le contexte **et le PDF source**. Pour un PDF partagé, elle ne lit que les pages
indiquées dans `source.pages`. Lui demander le [JSON de correction](docs/correction_format.md),
sans total ni note finale. Une copie illisible doit être revue avant import ; ne pas inventer des points.

5. Importer chaque réponse, calculer et exporter :

```sh
python -m moteur import-correction correction.json --db db/classe.sqlite
python -m moteur calculate --db db/classe.sqlite --sujet 1
python -m moteur render --db db/classe.sqlite --sujet 1 --output exports/evaluation-1 --pdf
```

Les identifiants ci-dessus sont des exemples : utiliser ceux retournés par votre base.
Le [manifeste](docs/evaluation_format.md#manifeste-du-pipeline) évite de saisir ces identifiants
pour un lot complet. `python -m moteur --help` liste les commandes.

## Responsabilités et état

- **SQLite** : sujet, versions, corrigés, grilles, items, copies logiques, pages de PDF, corrections, annotations, conseils et groupes normalisés.
- **Markdown** : mémoire par classe et grilles lisibles ; aucune modification automatique des règles pédagogiques.
- **Python** : validation stricte, transactions, calcul configurable, orchestration, exports et contexte IA.
- **LaTeX** : rendu des notes, bilan par item, annotations, conseils et corrigé de la version.
- **IA** : intervention extérieure au moteur pour proposer les grilles et interpréter les copies.

[Configuration des notes](configs/README.md) · [Modèle et migration](docs/data_model.md) ·
[Architecture](docs/architecture.md) · [Rendu](latex/README.md)

Les annotations localisées sont enregistrées et listées dans la fiche ; leur superposition sur
le PDF original n'est pas encore implémentée. La proposition automatique de grille et l'appel
à un fournisseur IA restent hors du pipeline déterministe. La validation sur une vraie
évaluation nécessite de fournir le sujet, son corrigé, les copies et les groupes réels.
