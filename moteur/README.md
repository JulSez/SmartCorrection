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


## Import de classe et identité globale (schéma v6)

`python -m moteur import-classe classe.csv --classe TMEX --db db.sqlite --preview`
renvoie les candidats, les lignes proches et une `empreinte` de vérification. Pour confirmer hors GUI,
passer `--rapprochements decisions.json`. Ce fichier contient `empreinte` et une liste `rapprochements`,
avec une décision par ligne : `{"id": 42}`, `{"nouveau": true}`, `{"ligne": 1}` pour reprendre une ligne
précédente, ou `{"id": 42, "fusionner": 17}` pour une consolidation explicitement affichée dans l’aperçu.
La classe et les contenus doivent rester identiques entre vérification et import. Les cas ambigus ne
sont jamais tranchés automatiquement. `eleve_par_classe` expose les anciens numéros aux imports CLI ;
les IDs visibles dans l’interface, ses groupes et ses rendus sont globaux.
