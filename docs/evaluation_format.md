# Format d'import d'une évaluation

Une évaluation peut être préparée dans un fichier JSON puis injectée dans SQLite.

## Exemple

```json
{
  "sujet": {
    "classe": "2nde A",
    "chapitres": "Calcul littéral ; équations",
    "type": "interrogation",
    "titre": "Évaluation 1",
    "date_evaluation": "2026-09-15",
    "config_notes": {
      "note_individuelle": {"max": 15},
      "note_groupe": {"max": 5, "mode": "moyenne_camarades"},
      "note_finale": {"max": 20, "arrondi": 0.5}
    }
  },
  "versions": [
    {
      "version": "A",
      "str_latex": "...",
      "corrige_latex": "..."
    }
  ],
  "grille": {
    "nom": "Grille principale",
    "exercices": [
      {
        "numero": "1",
        "titre": "Équations",
        "questions": [
          {
            "numero": "1",
            "texte": "Résoudre l'équation",
            "items": [
              {
                "code": "E1Q1I1",
                "description": "Transformation correcte",
                "bareme_max": 1.0,
                "regle_correction": "Ne pas repénaliser une erreur de signe propagée."
              }
            ]
          }
        ]
      }
    ]
  }
}
```

## Objectif

Ce format sert d'interface stable entre la préparation pédagogique et la base locale. L'identifiant SQLite du sujet est généré lors de l'import.
