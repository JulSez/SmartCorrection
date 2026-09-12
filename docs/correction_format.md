# Contrat JSON de correction IA

L'IA rend **un objet JSON strict**, sans bloc Markdown autour, sans note globale calculée.
Le moteur rejette les champs inconnus, clés répétées, NaN/Infinity, nombres sous forme de texte
et booléens à la place de nombres. Toute erreur annule l'import entier.

Exemple d'import individuel (les identifiants viennent de `prepare-ai`, jamais d'une supposition) :

```json
{
  "copie_id": 42,
  "grille_id": 3,
  "items": [
    {
      "item_code": "E1Q1I1",
      "points_obtenus": 1.5,
      "statut": "partiel",
      "annotation": "Erreur de signe à la deuxième étape.",
      "commentaire": "Méthode correcte ; erreur propagée non pénalisée à nouveau."
    }
  ],
  "annotations": [
    {
      "item_code": "E1Q1I1",
      "page": 1,
      "x": 0.15,
      "y": 0.30,
      "largeur": 0.5,
      "hauteur": 0.08,
      "texte": "Vérifier le changement de signe.",
      "type_annotation": "remarque"
    }
  ],
  "conseils": [
    {
      "item_code": "E1Q1I1",
      "texte": "Vérifier la solution dans l'équation initiale.",
      "priorite": 1
    }
  ],
  "commentaire_global": "La démarche est comprise. Soigner les signes."
}
```

Cet exemple suppose une grille contenant uniquement cet item et un barème d'au moins 1,5.
Pour une grille réelle, inclure **exactement une entrée pour chaque item**, même pour une
question sans réponse (`points_obtenus: 0`, `statut: "non_repondu"`). Aucun item supplémentaire,
manquant ou répété. Les codes sont recherchés dans la grille de cette copie, jamais globalement.

| Objet | Obligatoire | Facultatif |
|---|---|---|
| Racine, import individuel | `copie_id`, `grille_id`, `items` | `annotations`, `conseils`, `commentaire_global` |
| `items[]` | `item_code`, `points_obtenus` | `statut`, `annotation`, `commentaire` |
| `annotations[]` | `item_code`, `page`, `texte` | `x`, `y`, `largeur`, `hauteur`, `type_annotation` |
| `conseils[]` | `texte` | `item_code`, `priorite` |

- Identifiants et pages : entiers strictement positifs, première page = 1.
- Points : nombre fini entre 0 et le barème de l'item, bornes incluses.
- Statut : `acquis`, `partiel`, `non_acquis`, `non_repondu` ou `null`. Informatif : les points
  déterminent la note. Il n'y a pas de conversion implicite du statut en score.
- Textes fournis : chaînes non vides ; `commentaire_global`, `annotation`, `commentaire` et
  `type_annotation` acceptent `null`. Ce sont des textes simples, échappés pour LaTeX.
- `annotation` dans un item : remarque textuelle sans position. `annotations[]` : remarques
  localisées, obligatoirement reliées à un item. Les deux apparaissent dans la fiche.
- Coordonnées : fractions entre 0 et 1, origine en haut à gauche, x vers la droite, y vers le bas.
  Fournir x et y ensemble ou les omettre ensemble. Les dimensions nécessitent une position ;
  x + largeur et y + hauteur ne dépassent pas 1. Valeurs facultatives `null` acceptées.
  La page doit exister dans le PDF fourni à l'IA ; sa borne supérieure n'est pas vérifiée par l'import.
- Conseil : `item_code` peut être omis/null pour un conseil général ; s'il est présent, il doit
  appartenir à cette grille. Priorité : entier positif (1 d'abord), ou omise/null.
- Listes facultatives : omettre ou fournir `[]`, jamais `null`.
- La grille doit être validée et compatible avec le sujet et la version. Une copie absente
  ne reçoit pas de correction. Une copie illisible demande une revue humaine, pas un zéro inventé.

La somme est recalculée depuis `CorrectionItem`. Ne jamais fournir `note_brute`, `note_finale`,
les notes des camarades ou des conseils contenant des notes calculées hors du moteur.
Appliquer les règles du barème et les remarques pédagogiques de la classe ; en particulier,
ne pas repénaliser une erreur propagée sauf règle explicite.

## Préparation du contexte

`prepare-ai` écrit sur stdout le sujet/version, le corrigé, la grille, la mémoire Markdown
et les savoir-faire fournis, ainsi qu'un squelette JSON. Les points y sont `null` volontairement :
le squelette n'est pas importable tant que l'IA ne l'a pas rempli. Le PDF est à joindre séparément.
Aucun service IA n'est appelé et aucun fichier n'est transmis automatiquement.

## Lots et remplacement

Dans le manifeste `run`, les fichiers omettent obligatoirement `copie_id` et `grille_id`.
Le manifeste associe chaque fichier au numéro d'élève ; le moteur résout ces identifiants.
Voir les [exemples importables](../examples/tmex_demo/).

Une correction existante n'est pas écrasée par défaut. `--replace` remplace atomiquement
items, annotations, conseils et commentaire, conserve l'identité de correction et invalide
les notes finales en cache du sujet. Une erreur pendant le remplacement restaure l'ancienne
correction entière. Il n'y a pas d'historique des révisions : sauvegarder la base si nécessaire.
