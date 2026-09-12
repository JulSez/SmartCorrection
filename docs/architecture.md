# Architecture SmartCorrection

## Les quatre briques

### 1. Grille
La grille est proposée à partir du sujet, des savoir-faire et des remarques historiques de la classe.

### 2. Correction / annotation
Chaque copie produit une correction structurée : score par item, annotations et conseils.

### 3. Calcul des notes
Le calcul est déterministe et réalisé localement par Python à partir des données de correction et des groupes.

### 4. Croisement grille / correction / annotation
Les annotations et scores sont reliés aux items de grille grâce à des identifiants stables.

## Séparation des responsabilités

- **Markdown** : mémoire pédagogique et références.
- **SQLite** : données structurées et état réel des corrections.
- **Python** : calculs et orchestration.
- **LaTeX** : rendu.
- **IA** : proposition de grille et interprétation des copies.

## Flux cible

```text
Sujet + savoir-faire + classe
          ↓
    proposition de grille
          ↓
       copies PDF
          ↓
 correction structurée IA
          ↓
        SQLite
          ↓
 moteur de notes Python
          ↓
 préparation des données
          ↓
      LaTeX / exports
```

## Principe de reproductibilité

Toute note finale doit pouvoir être recalculée à partir de la base et de la configuration du sujet, sans dépendre d'une conversation passée.
