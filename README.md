# SmartCorrection

Moteur **local**, Python 3.11+ et SQLite, sans appel IA pour les imports, les calculs ou les exports.
Les calculs et imports CLI sont sans dépendance Python externe ; l’interface et les exports PDF utilisent `pypdf`. L'IA propose le barème et interprète les copies ;
l'enseignant valide la grille, et Python calcule les notes à partir de chaque item.

## Interface graphique

Sous Windows, double-cliquer sur **`Lancer-SmartCorrection.cmd`**. Ou, depuis le dépôt :

```sh
python -m pip install ".[gui]"
python -m moteur gui
```

Le navigateur s’ouvre sur une application locale avec deux boutons : **Ajouter une classe**
(CSV nom/prénom) et **Corriger un paquet de copies**.

Le parcours comporte quatre écrans : **Barème → Calibrage → Correction complète → Résultats**.
Chaque consigne s’affiche directement : la copier dans la même conversation IA, y joindre les
PDF, puis coller le JSON final dans l’application. Le premier calibrage rassemble l’inventaire,
les corrigés de référence et jusqu’à cinq corrections ; les lots suivants ne répètent plus les
éléments déjà enregistrés. Les ajustements de calibrage signalent les anciennes copies à reprendre.
Les consignes générales et de classe peuvent être réécrites en fin de correction et conservées dans SQLite.

**LaTeX reste le moteur de rendu mathématique.** `pypdf` assemble les PDF.
Le format par défaut est A5 paysage : fiche de correction à gauche, corrigé à droite, en deux
zones A6 portrait. La fiche regroupe les points et les erreurs par question dans un tableau compact,
avec des conseils facultatifs. Les formats et l’assemblage sont configurables.
La note est individuelle sur 20 par défaut. L’option Maths expertes ajoute individuel /15 +
moyenne des autres camarades /5 ; les identités et groupes restent locaux.

[Installation, parcours et formats des réponses IA](docs/interface.md)

## Premier pipeline en ligne de commande

Depuis la racine du dépôt :

```sh
python -m pip install ".[gui]"
python -m unittest discover -s tests -v
python -m moteur run examples/tmex_demo/pipeline.json --db db/demo.sqlite --output exports/demo
```

Produit `notes.json`, `notes.csv`, un `.tex` par élève, les grilles en Markdown et un manifeste SHA-256 des sorties.
Pour compiler aussi les PDF, ajouter `--pdf` (TeX Live : LaTeX, AMS, Latin Modern,
Geometry, Longtable, xcolor/colortbl ; français recommandé), avec `python -m pip install ".[pdf]"`
si l’interface n’est pas installée. Le français est utilisé si `french.ldf` est installé.
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

SmartCorrection peut conserver **un seul PDF source pour toute l'évaluation**. Une copie logique
référence simplement une ou plusieurs pages de ce PDF. Elle peut être rattachée à un élève dès
l'import, ou rester **non attribuée** si le nom/numéro n'est pas lisible sur la copie.

Exemple `private/copies.csv` :

```csv
numero;version;pages;statut
1;A;1;present
2;B;2;present
;A;3-4;present
4;B;;absent
```

La ligne sans `numero` crée une copie non attribuée pour les pages 3-4. Une absence doit toujours
être rattachée à un élève.

Puis :

```sh
smartcorrection import-copies private/copies.csv --sujet 1 --pdf private/copies.pdf --db db/1gspe.sqlite
```

`pages` accepte un numéro, une plage (`3-5`) ou plusieurs valeurs (`1,3-5`, à citer si le CSV
utilise la virgule comme séparateur). Une même page d'un même PDF ne peut pas être affectée à
deux copies. Un nouvel import identique est idempotent. Avant correction, `--replace` permet de
corriger une association.

Une copie non attribuée peut être corrigée normalement : `prepare-ai` fonctionne avec son
`copie_id`, son PDF et ses pages. Quand son identité est connue, il suffit de réimporter une ligne
avec le même PDF, la même version et les mêmes pages mais avec `numero` rempli ; SmartCorrection
rattache alors la copie existante à l'élève, sans recréer la correction. Après correction, la
version, le PDF et les pages restent figés ; seul le passage « non attribuée → élève identifié »
reste autorisé.

En ligne de commande, le calcul final des notes est volontairement bloqué tant qu'il reste au moins une copie non
attribuée, afin de ne pas perdre silencieusement une correction.

`prepare-ai` renvoie `source.pdf_path` et `source.pages`. Pour une copie issue d'un PDF partagé,
les annotations utilisent les numéros de page du PDF source.

## Utilisation CLI sur une vraie évaluation

1. Importer la classe depuis un CSV local, puis préparer `classes/<classe>.md`, les savoir-faire
   et le JSON d'évaluation suivant [le contrat](docs/evaluation_format.md). Le JSON peut ne contenir
   encore aucune copie.
2. Relire la grille ; inscrire `validee: true` seulement après cette revue, ou la valider en CLI.
3. Importer l'évaluation, puis associer les pages du PDF source. Les copies illisibles peuvent
   rester sans numéro à ce stade :

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

5. Importer chaque réponse, attribuer les éventuelles copies encore anonymes, calculer et exporter :

```sh
python -m moteur import-correction correction.json --db db/classe.sqlite
python -m moteur calculate --db db/classe.sqlite --sujet 1
python -m moteur render --db db/classe.sqlite --sujet 1 --output exports/evaluation-1 --pdf
```

Les identifiants ci-dessus sont des exemples : utiliser ceux retournés par votre base.
Le [manifeste](docs/evaluation_format.md#manifeste-du-pipeline) évite de saisir ces identifiants
pour un lot complet. `python -m moteur --help` liste les commandes.

## Responsabilités et état

- **SQLite** : données de correction normalisées, consignes pédagogiques versionnées et dossiers de l’interface.
- **Markdown** : grilles lisibles et anciens fichiers de classe ; l’interface migre une fois leur contenu vers SQLite.
- **Python** : validation stricte, transactions, calcul configurable, orchestration, exports et contexte IA.
- **LaTeX** : rendu des notes, bilan par item, annotations, conseils et corrigé de la version.
- **IA** : intervention extérieure au moteur pour proposer les grilles et interpréter les copies.

[Configuration des notes](configs/README.md) · [Modèle et migration](docs/data_model.md) ·
[Architecture](docs/architecture.md) · [Rendu](latex/README.md)

Les annotations localisées sont enregistrées et listées dans la fiche ; leur superposition sur
le PDF original n'est pas encore implémentée. La proposition automatique de grille et l'appel
à un fournisseur IA restent hors du pipeline déterministe. La validation sur une vraie
évaluation nécessite de fournir le sujet, son corrigé et les copies réelles (ainsi que les groupes
si le parcours CLI les utilise).

### Deux niveaux de grille

La grille détaillée par item reste la référence pour l’IA, SQLite et les calculs. Le JSON
de correction conserve chaque item et ses points. La fiche élève affiche un **bilan par question** :
somme des points / barème de la question, puis seulement les erreurs des items ayant perdu des
points. Les retours identiques sont affichés une seule fois par question ; les critères et les
commentaires sur les items entièrement réussis ne sont pas répétés. Une question réussie
conserve sa note, avec une case d’erreurs vide. Les données détaillées et les exports JSON
restent inchangés ; les totaux des questions ne recalculent pas la note finale.
