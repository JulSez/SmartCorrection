# Modèle SQLite et migration

`moteur/schema.sql` est le schéma distribué ; `db/schema.sql` est sa copie documentaire,
vérifiée par un test. `PRAGMA user_version = 2`. Les connexions du moteur activent les clés
étrangères et sont fermées explicitement ; toute écriture d'import utilise une transaction.

| Relation | Règle |
|---|---|
| Élève | Identité `(classe, numero)` unique ; nom/prénom facultatifs |
| Sujet → versions → corrigé | Nom de version unique par sujet, un corrigé par version |
| Sujet → copies | Une copie par élève et sujet ; statut `present` ou `absent` |
| Sujet → grilles | Une commune et/ou une par version ; validation pédagogique explicite |
| Grille → exercice → question → item | Numéros locaux uniques ; codes d'items uniques par grille |
| Copie → correction | Une correction ; grille compatible avec le sujet et la version |
| Correction → CorrectionItem | Une ligne par item, points dans les limites du barème |
| Correction → annotation | Item de la même grille obligatoire ; page et coordonnées |
| Correction → conseil | Item de la même grille facultatif |
| Sujet → groupe → GroupeEleve | Un élève appartient au plus à un groupe du même sujet |
| evaluation_import | Clé et empreinte du lot initial, sujet unique associé |

`item.grille_id` sert à l'unicité locale des codes. Un trigger vérifie que la question appartient
bien à cette grille. Les structures ne sont pas stockées en gros tableaux JSON ; seul
`sujet.config_notes`, petit objet de paramètres sans relations métier, reste en JSON.
Les chapitres restent un texte descriptif, comme dans le schéma initial.

Les contraintes SQL contrôlent notamment les liens classe/sujet/version/grille, les limites de
points, les doubles inscriptions de groupe et les références d'annotation/conseil. Des triggers
figent une grille déjà utilisée, y compris l'ajout d'items, et empêchent de déplacer les identités
parentes utilisées. Les validations applicatives ajoutent les contrôles de JSON strict et de
complétude des corrections : une écriture SQL manuelle n'est pas une alternative à l'import.

`correction.note_brute` et `note_finale` sont des **caches**, jamais des entrées du calcul.
Le moteur recalcule depuis tous les `correction_item` et la configuration courante. Modifier
un groupe ou une configuration par SQL impose de recalculer avant de lire ces caches ;
`render` le fait systématiquement. La note individuelle et celle de groupe sont produites
à la demande et exportées, sans nouvelle table de calcul inutile.

## Bases initiales

```sh
python -m moteur init-db --db db/smartcorrection.sqlite
```

La migration depuis le schéma initial conserve identifiants, scores, commentaires, conseils et
annotations, reconstruit `item` pour l'unicité par grille et ajoute le statut de copie ainsi que
la validation de grille. La migration est transactionnelle et vérifie `foreign_key_check`.
Les anciens barèmes sont marqués non validés : après revue, `validate-grid` les rend calculables.
Une ancienne correction incomplète doit être remplacée par une correction complète.

Les doublons incompatibles avec les nouvelles contraintes provoquent un arrêt **sans suppression
ni migration partielle**. Ils doivent être résolus sur la base concernée. Le moteur refuse aussi
une version de base future. Une sauvegarde SQLite avant migration permet un retour au moteur ancien.

## Fichiers et portabilité

Les chemins des PDF deviennent absolus à l'import : déplacer le projet impose de mettre à jour
ces chemins dans la base. Les LaTeX des versions/corrigés et la configuration restent dans SQLite.
Les Markdown pédagogiques vivent séparément et sont ajoutés au contexte IA sur demande. Les
exports contiennent leurs données de rendu et les sommes de contrôle des fichiers finaux.
Le manifeste de sortie n'est pas une sauvegarde de la base ni des PDF sources.
