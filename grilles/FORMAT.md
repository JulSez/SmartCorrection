# Format des grilles

Une grille décrit le barème d’un sujet de manière hiérarchique :

- exercice ;
  - question ;
    - item de correction.

Chaque item doit avoir au minimum :
- un identifiant stable ;
- une description courte ;
- un barème maximal ;
- éventuellement une règle ou remarque de correction.

## Exemple

```md
# Grille — Sujet 001

## Exercice 1

### Question 1

- `E1Q1I1` — Mise en équation correcte — 1 pt
- `E1Q1I2` — Résolution correcte — 1,5 pt
- `E1Q1I3` — Conclusion — 0,5 pt
```

Les grilles proposées doivent s’appuyer sur :
1. le sujet ;
2. les savoir-faire associés ;
3. le fichier de la classe ;
4. les remarques pédagogiques déjà accumulées.
