# Modèle de données

## Entités principales

### Élève
Identité minimale d'un élève dans une classe.

### Sujet
Évaluation commune à une classe. Contient les métadonnées et la configuration de calcul des notes.

### Version
Variante d'un sujet. Une copie peut référencer explicitement sa version.

### Corrigé
Corrigé LaTeX associé à une version.

### Copie
PDF d'un élève pour un sujet et éventuellement une version.

### Grille
Barème associé à un sujet, éventuellement spécifique à une version.

### Exercice → Question → Item
Hiérarchie normalisée du barème. L'item est l'unité atomique de notation.

### Correction
Correction globale d'une copie.

### CorrectionItem
Score et commentaire pour un item précis. C'est la donnée source du calcul de la note brute.

### Annotation
Annotation localisée sur une page du PDF.

### Conseil
Conseil pédagogique relié à la correction, éventuellement à un item.

### Groupe / GroupeÉlève
Composition des groupes pour un sujet.

## Principes

- Les notes calculées ne remplacent jamais les données brutes par item.
- La configuration du calcul doit être conservée avec le sujet pour permettre le recalcul.
- Les fichiers PDF restent sur disque et la base stocke leur chemin.
- Les contenus LaTeX des sujets/corrigés peuvent être stockés en base car ils font partie de l'état reproductible de l'évaluation.
