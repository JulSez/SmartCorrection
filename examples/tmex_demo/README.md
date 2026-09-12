# Démonstration fictive TMex

Ces scores sont inventés pour tester le logiciel. Aucun PDF de copie réelle n'est fourni.
La structure reprend le besoin interro /15 + camarades /5. Le groupe contient les numéros
2, 31, 3 et 22 ; le numéro 22 est absent. La version B utilise volontairement un barème /30.

Résultats attendus : 2 → 12 + 4 = 16 ; 31 → 15 + 3,5 = 18,5 ;
3 → 9 + 4,5 = 13,5 ; 22 → ABS. L'élève lui-même et les absents exclus
ne participent pas à la moyenne des camarades.

Depuis la racine :

```sh
python -m moteur run examples/tmex_demo/pipeline.json --db db/demo.sqlite --output exports/demo --pdf
```

Pour rejouer : nouveau dossier de sortie et `--replace`, ou nouvelle base.
Ne pas utiliser `--check-pdfs` sur cette démonstration sans copies sources.
