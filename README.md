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

## Utilisation sur une vraie évaluation

1. Préparer `classes/<classe>.md`, les savoir-faire et le JSON d'évaluation suivant
   [le contrat](docs/evaluation_format.md). Les chemins des copies sont relatifs au JSON.
2. Relire la grille ; inscrire `validee: true` seulement après cette revue, ou la valider en CLI.
3. Importer l'évaluation et les copies, puis préparer le contexte à transmettre à l'IA :

```sh
python -m moteur import-evaluation evaluation.json --db db/classe.sqlite --check-pdfs
python -m moteur validate-grid --db db/classe.sqlite --grille 1
python -m moteur prepare-ai --db db/classe.sqlite --copie 1 --classe-md classes/TMex.md --savoir-faire savoir-faire/equations.md > contexte.json
```

4. Fournir à l'IA le contexte **et le PDF de la copie**. Lui demander le
   [JSON de correction](docs/correction_format.md), sans total ni note finale.
   Une copie illisible doit être revue avant import ; ne pas inventer des points.
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

- **SQLite** : sujet, versions, corrigés, grilles, items, copies, corrections, annotations, conseils et groupes normalisés.
- **Markdown** : mémoire par classe et grilles lisibles ; aucune modification automatique des règles pédagogiques.
- **Python** : validation stricte, transactions, calcul configurable, orchestration, exports et contexte IA.
- **LaTeX** : trois colonnes de notes, détails des camarades en petit, bilan par item, annotations, conseils et corrigé de la version.
- **IA** : intervention extérieure au moteur pour proposer les grilles et interpréter les copies.

[Configuration des notes](configs/README.md) · [Modèle et migration](docs/data_model.md) ·
[Architecture](docs/architecture.md) · [Rendu](latex/README.md)

Les annotations localisées sont enregistrées et listées dans la fiche ; leur superposition sur
le PDF original n'est pas encore implémentée. La proposition automatique de grille et l'appel
à un fournisseur IA restent hors du pipeline déterministe. La validation sur une vraie
évaluation nécessite de fournir le sujet, son corrigé, les copies et les groupes réels.
