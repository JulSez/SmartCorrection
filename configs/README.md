# Configuration des notes

La configuration JSON est conservée dans `sujet.config_notes`. Aucun `eval`, Python injecté
ou logique de calcul LaTeX. Les clés inconnues, nombres non finis, booléens numériques et
options mal orthographiées sont rejetés. Toutes les sections sont facultatives, mais pas `null`.

```json
{
  "note_individuelle": {"max": 15, "arrondi": null},
  "note_groupe": {
    "max": 5,
    "mode": "moyenne_camarades",
    "arrondi": null,
    "sans_camarades": "zero"
  },
  "note_finale": {
    "max": 20,
    "arrondi": 0.5,
    "arrondi_mode": "demi_superieur",
    "poids_individuel": 1,
    "poids_groupe": 1,
    "bonus": 0
  },
  "absences": {"mode": "exclure"}
}
```

Cet exemple donne tous les défauts. Les maxima individuel/final et les pas d'arrondi sont
strictement positifs ; maximum groupe, poids et bonus sont positifs ou nuls.

| Paramètre | Effet |
|---|---|
| `moyenne_camarades`, `mediane_camarades` | Excluent l'élève lui-même |
| `moyenne_groupe`, `mediane_groupe` | Incluent l'élève lui-même |
| `aucun` | Note groupe égale à zéro |
| `sans_camarades: zero` | Note groupe nulle en l'absence de valeur disponible |
| `sans_camarades: individuelle` | Utilise la note individuelle comme base de conversion |
| `sans_camarades: erreur` | Bloque le calcul tant qu'aucune valeur n'est disponible |
| `absences.mode: exclure` | ABS, note finale `null`, retiré du calcul des camarades |
| `absences.mode: zero` | Note finale 0 pour l'absent, valeur 0 incluse pour ses camarades |
| `arrondi: null` | Aucun arrondi à cette étape |
| `demi_superieur` | En cas d'égalité entre deux multiples, choisit le supérieur : 14,25 → 14,5 au pas 0,5 |
| `pair` | Égalités vers le multiple dont l'indice est pair |
| `inferieur`, `superieur` | Arrondi vers le multiple inférieur ou supérieur |

Ordre des opérations : somme des `correction_item` ; conversion du barème de la grille sur
le maximum individuel ; arrondi individuel et plafond ; agrégation des notes individuelles
disponibles du groupe ; conversion sur le maximum groupe ; arrondi groupe et plafond ;
`poids_individuel × note_individuelle + poids_groupe × note_groupe + bonus` ;
plafond, arrondi final puis plafond à nouveau. Le bonus ne s'applique pas aux absents.
Les notes des camarades affichées sont exactement les notes individuelles utilisées.

Une copie présente non corrigée ou une correction incomplète **bloque** le calcul, sans
assimilation à une absence. Un membre de groupe doit avoir une copie présente ou absente.
Les élèves sans groupe suivent `sans_camarades` ; le mode `*_groupe` inclut leur propre note.

La précision décimale est utilisée pour les sommes de points et les arrondis. SQLite stocke
des `REAL` et les agrégations utilisent des flottants ; l'objectif de reproductibilité porte
sur les notes et les données exportées, pas sur l'identité binaire des PDF horodatés par LaTeX.
