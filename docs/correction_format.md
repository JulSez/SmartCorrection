# Format d'échange d'une correction

L'IA ne doit pas renvoyer une note opaque. Elle renvoie une structure exploitable localement et reliée à la grille.

## Exemple JSON

```json
{
  "copie_id": 42,
  "grille_id": 3,
  "items": [
    {
      "item_code": "E1Q1I1",
      "points_obtenus": 1.0,
      "statut": "acquis",
      "annotation": "Mise en équation correcte.",
      "commentaire": null
    },
    {
      "item_code": "E1Q1I2",
      "points_obtenus": 0.5,
      "statut": "partiel",
      "annotation": "Erreur de signe à la deuxième étape.",
      "commentaire": "La méthode est correcte ; l'erreur est propagée sans double pénalisation."
    }
  ],
  "conseils": [
    {
      "item_code": "E1Q1I2",
      "texte": "Vérifier les changements de signe lors du passage d'un terme d'un membre à l'autre.",
      "priorite": 1
    }
  ],
  "commentaire_global": "Ensemble maîtrisé, attention aux signes."
}
```

## Règles

- `item_code` doit correspondre à un item existant dans la grille.
- `points_obtenus` doit rester entre 0 et le barème maximal de l'item.
- Une même erreur propagée ne doit pas être pénalisée plusieurs fois sauf règle explicite de la grille.
- Les conseils doivent être concis et actionnables.
- La note brute est recalculée localement depuis les items : elle n'a pas besoin d'être fournie par l'IA.
