# SmartCorrection

SmartCorrection est un moteur local de correction et de production de notes pour des évaluations de mathématiques.

## Principes

- **SQLite** stocke les données structurées : élèves, sujets, versions, copies, grilles, corrections et groupes.
- **Markdown** stocke les règles pédagogiques, les remarques par classe et les savoir-faire.
- **Python** assure les calculs, l’orchestration et les exports.
- **LaTeX** assure le rendu des corrigés, annotations et documents finaux.
- L’IA intervient surtout pour proposer les grilles et interpréter les copies ; les calculs déterministes restent locaux.

## Architecture

```text
SmartCorrection/
├── classes/            # mémoire pédagogique par classe
├── grilles/            # grilles d’évaluation en Markdown
├── savoir-faire/       # références et savoir-faire
├── moteur/             # logique Python
├── configs/            # paramètres de calcul
├── latex/              # templates et rendus LaTeX
├── db/                 # schéma SQLite
├── exports/            # sorties locales générées
└── docs/               # documentation technique
```

## Pipeline cible

1. Décrire le sujet et ses versions.
2. Générer/proposer une grille à partir des savoir-faire et des remarques de classe.
3. Corriger les copies en produisant une correction structurée.
4. Enregistrer les données dans SQLite.
5. Calculer les notes via le moteur Python configurable.
6. Générer les documents finaux via LaTeX.

## État

Initialisation du projet en cours. Le schéma SQLite et le moteur de notes seront ajoutés ensuite.
