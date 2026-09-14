# Contrat JSON d'évaluation

Référence exécutable : [`examples/tmex_demo/evaluation.json`](../examples/tmex_demo/evaluation.json).
Les structures imbriquées sont un format d'échange ; l'import les normalise dans SQLite.
Le JSON doit être strict : pas de commentaire, clé répétée, NaN, Infinity ou clé inconnue.
Les numéros d'exercice/question sont des **chaînes** ; les numéros d'élève/groupe sont des
**entiers strictement positifs**. Les textes fournis sont non vides ; les textes facultatifs
peuvent être `null` sauf mention contraire. Les listes obligatoires sont non vides.

| Objet | Champs obligatoires | Champs facultatifs |
|---|---|---|
| Racine | `sujet`, `versions`, exactement `grille` ou `grilles` | `cle`, `eleves`, `copies`, `groupes` |
| `sujet` | `classe` | `chapitres` (texte), `type`, `titre`, `date_evaluation` (texte), `config_notes` (objet) |
| `versions[]` | `version`, `str_latex` | `corrige_latex` |
| `grille` / `grilles[]` | `exercices` | `nom`, `version`, `validee` (booléen, défaut false), `total_points` |
| `exercices[]` | `numero`, `questions` | `titre` |
| `questions[]` | `numero`, `items` | `texte` |
| `items[]` | `code`, `description`, `bareme_max` | `regle_correction` |
| `eleves[]` | `numero` | `nom`, `prenom`, `eleve_id` global déjà connu |
| `copies[]` | `numero`, `version`, `pdf_path` si présent | `statut` (`present` par défaut ou `absent`) |
| `groupes[]` | `numero`, `eleves` (liste de numéros) | aucun |

`cle` identifie durablement le lot. Un import identique retrouve le même sujet sans doublons.
Un contenu différent sous la même clé est rejeté ; un autre sujet doit avoir une autre clé.
Sans clé, l'empreinte SHA-256 du JSON canonique sert de clé. Les tableaux restent ordonnés.
Cet import n'est pas un éditeur de sujet existant : les modifications ultérieures explicites
se font dans la base, avec les contraintes décrites dans le modèle.

Les versions ont des noms distincts. Chaque grille vise une version déclarée ou est commune
(`version` omise/null). Une seule grille commune et une seule grille par version sont admises.
Le pipeline choisit la grille spécifique si elle existe, sinon la commune. Les codes d'items
sont uniques **dans leur grille**, et peuvent être réutilisés dans une autre version ou évaluation.
Les barèmes sont finis et positifs ou nuls ; leur somme doit être strictement positive.
`total_points`, si fourni, est vérifié contre cette somme (tolérance 1e-9).

Une grille non validée peut être importée pour préparation. Une correction exige sa validation
humaine (`validee: true` dans l'import ou commande `validate-grid`). Une fois utilisée, sa
structure et ses barèmes sont figés. Les grilles lisibles peuvent être exportées en Markdown
avec les autres sorties ; le fichier Markdown de référence n'est jamais écrasé implicitement.

Les anciens imports CLI utilisent encore `(classe, numero)` dans la table des inscriptions. L’identité est désormais `eleve.id`, globale à toutes les classes. Fournir `eleve_id` pour associer explicitement une identité connue à une inscription. Sans cet ID, une identité ressemblante dans la base bloque la création : importer la classe dans l’interface pour confirmer le rapprochement. Les noms déjà présents ne sont pas écrasés.
Chaque copie et membre doit référencer un élève déclaré dans le lot. Une seule copie par
élève/sujet et un seul groupe par élève/sujet. Le chemin PDF est résolu depuis le dossier du
JSON et stocké en chemin absolu. `--check-pdfs` vérifie son existence, pas la validité du PDF.
Pour un absent, `pdf_path` peut être omis ou vide. Une absence ne reçoit pas de correction.

`str_latex` et `corrige_latex` contiennent des **fragments de corps LaTeX**, sans préambule ni
commande de début/fin de document. Échapper chaque antislash dans JSON, par exemple :

```json
{"str_latex": "Calculer $\\frac{1}{2}+1$."}
```

Utiliser un sérialiseur JSON pour éviter les erreurs d'échappement.

## Manifeste du pipeline

```json
{
  "evaluation": "evaluation.json",
  "corrections": [
    {"numero": 2, "file": "correction_2.json"},
    {"numero": 31, "file": "correction_31.json"}
  ]
}
```

Les chemins sont relatifs au manifeste. Une seule correction par numéro.
Dans ces fichiers de correction, **omettre** `copie_id` et `grille_id` : le pipeline les résout
à partir du sujet importé, du numéro d'élève et de sa version. Il rejette ces identifiants s'ils
sont fournis afin d'éviter une affectation à une ancienne base.

```sh
python -m moteur run pipeline.json --db db/classe.sqlite --output exports/lot-1 --check-pdfs --pdf
```

La création/migration du schéma est une étape préalable. Le lot de données (évaluation,
corrections et calculs) est une transaction : une erreur annule toutes les nouvelles écritures.
La génération se fait dans un dossier temporaire, publié uniquement après tous les rendus réussis.
Un arrêt matériel au moment exact de la publication des fichiers/du commit SQLite ne peut pas
être atomique entre disque et base ; choisir alors un nouveau dossier et relancer le lot.

