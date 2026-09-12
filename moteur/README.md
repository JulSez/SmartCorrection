# Modules

- `validation.py` : JSON strict et primitives de validation.
- `db.py`, `schema.sql` : accès SQLite, transactions et migration v1 → v2.
- `import_evaluation.py` : sujet, versions, corrigés, grilles, élèves, copies, groupes.
- `import_correction.py` : correction complète, annotations, conseils et remplacement atomique.
- `notes.py` : calcul pur et configuration.
- `calcul.py` : lecture des items et groupes, calcul d'une évaluation, actualisation des caches.
- `render.py` : fiches, CSV/JSON, Markdown des grilles, manifeste de sortie, compilation PDF.
- `pipeline.py` : CLI, orchestration transactionnelle, contexte IA.

Les fonctions d'import bas niveau recevant `conn` participent à la transaction de l'appelant.
Ne pas intercepter leur exception à l'intérieur d'une transaction puis la committer : utiliser
les wrappers `import_*_json` ou `run_pipeline` pour bénéficier de l'annulation automatique.

`python -m moteur` ou `smartcorrection` après installation. Tests sans dépendance :
`python -m unittest discover -s tests -v`.
