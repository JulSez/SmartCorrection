# Moteur

Le moteur Python doit rester générique et modulaire.

Responsabilités prévues :
- lire les données depuis SQLite ;
- calculer les notes à partir des items de correction ;
- appliquer les règles de pondération et de groupe ;
- préparer les données pour les templates LaTeX ;
- orchestrer les exports.

Le moteur ne doit pas contenir les données des élèves ni les règles pédagogiques spécifiques d'une classe.

## Modules cibles

- `db.py` : accès SQLite ;
- `notes.py` : calcul des notes ;
- `render.py` : préparation des rendus ;
- `pipeline.py` : orchestration globale.
