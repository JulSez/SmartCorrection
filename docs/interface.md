# Interface graphique locale

Depuis la racine du dépôt, avec Python 3.11 ou plus récent :

```sh
python -m pip install ".[gui]"
python -m moteur gui
```

Sous Windows, double-cliquer sur `Lancer-SmartCorrection.cmd`. Ce lanceur utilise `py -3`
ou `python`, installe la dépendance Python de l’interface si elle manque, puis ouvre le navigateur.
Garder la fenêtre de lancement ouverte. Ctrl+C arrête le serveur ; les données restent enregistrées.

L’application ouvre `http://127.0.0.1:8765`. Elle fonctionne sans serveur distant ni clé API.
Les échanges avec l’IA se font par copier-coller et pièces jointes dans une conversation
ouverte par l’enseignant. Ajouter un PDF dans SmartCorrection ne le transmet pas à l’IA.

LaTeX reste nécessaire pour les PDF : une distribution TeX Live ou MiKTeX avec `pdflatex`,
AMS, Geometry, Longtable et Latin Modern. Babel français est recommandé.
`pypdf` compte les pages des sources et assemble les PDF produits par LaTeX ; il ne compose
pas les formules. Sans LaTeX, les imports et les exports de sources `.tex` restent utilisables.

Par défaut, les fiches sont en **A5 paysage**, divisées en deux zones **A6 portrait** :
correction à gauche, corrigé à droite. La fiche contient les identifiants locaux, les notes,
un tableau **Question / Erreurs / Note** et les conseils facultatifs. Les formats,
colonnes du corrigé et assemblage se règlent dans l’interface. Les noms affichés localement
ne sont jamais ajoutés aux consignes IA. L’ancienne option « Saut après correction », devenue
sans effet avec le tableau compact, n’est plus proposée ; les réglages enregistrés restent compatibles.

L’aperçu PDF intégré autorise uniquement une page de la même origine locale à l’afficher.
Les pages de l’application restent interdites d’intégration ; les origines externes restent
bloquées. Si le lecteur PDF du navigateur est désactivé, utiliser « Ouvrir dans un onglet ».

Options :

```sh
smartcorrection-gui --db db/mon-travail.sqlite --data-dir private/mon-travail --port 8766 --no-browser
```

## Les deux boutons de l’accueil

**Ajouter une classe** importe un CSV `nom,prenom`. **Vérifier les élèves** compare les noms à
l’ensemble de la base : accents, casse, tirets, noms/prénoms composés et ressemblances orthographiques.
Chaque proposition montre l’ID permanent, le nom complet et les classes déjà connues. Aucun
rapprochement approximatif ou entre classes n’est appliqué automatiquement. Choisir l’élève existant,
**Nouvel élève** (homonyme), ou une ligne précédente du CSV (doublon), puis **Confirmer l’import**.
Les correspondances exactes déjà inscrites dans cette même classe sont présélectionnées lorsqu’elles
ne sont pas ambiguës. Les autres élèves de la base restent sélectionnables si la suggestion manque.
L’écran final affiche les IDs attribués. L’ID ne dépend ni de la classe ni de l’ordre du fichier.

Les colonnes de liste `numero` des anciens CSV ne définissent jamais l’ID global. Elles sont conservées
uniquement pour les anciens imports CLI. L’interface et ses groupes utilisent désormais l’ID global.
UTF-8 et Windows-1252 sont acceptés, avec virgule, point-virgule ou tabulation comme séparateur.
Un changement du fichier ou des identités après la vérification impose une nouvelle vérification.

Quand un élève déjà inscrit est rapproché d’un autre ID, l’option indique explicitement **Fusionner
ID … dans ID …**. Cette décision réaffecte ses copies et groupes sans perdre ses notes ; les anciennes
identités sont tracées dans un journal de fusion, les variantes de noms sont conservées. Deux copies
ou deux groupes différents pour la même évaluation empêchent la fusion : rien n’est modifié.

À la première ouverture d’une base antérieure, une sauvegarde `*.avant-identites-*.sqlite` est créée
à côté de la base. La migration conserve tous les IDs, inscriptions, copies et notes. Elle ne fusionne
aucun homonyme d’elle-même. Les anciens numéros de liste restent accessibles pour la compatibilité CLI.

**Corriger un paquet de copies** demande la classe et le titre, puis crée un dossier reprenable.
Les classes, dossiers, réponses en cours, documents générés et consignes survivent au redémarrage.

## Le parcours en quatre écrans

| Écran | Action | Résultat |
|---|---|---|
| Barème | Joindre les documents dans l’IA, discuter du barème, coller son JSON et cliquer sur « Valider et voir le barème » | Grille validée et PDF affiché |
| Calibrage | Importer le premier JSON complet, lire les fiches, discuter des ajustements dans l’IA, essayer le lot suivant | Inventaire, corrigés de référence, corrections d’essai |
| Correction complète | Copier la consigne actualisée et importer les réponses | Corrections de toutes les copies incluses |
| Résultats | Générer les documents, puis préparer les consignes de la prochaine fois | PDF, notes CSV, consignes enregistrées |

Garder **la même conversation IA** : les consignes ne répètent pas les longs corrigés déjà
validés. Si le contexte manque, l’IA doit le demander, jamais le reconstituer de mémoire.
Le premier JSON de calibrage contient l’inventaire complet, les corrigés de toutes les versions,
jusqu’à cinq corrections et une moyenne estimée. Les suivants omettent l’inventaire enregistré
et les références inchangées. La moyenne estimée est indicative, jamais une note cible.

Les ajustements se discutent directement dans la conversation IA, puis les corrections révisées
sont importées dans l’application. Il n’y a plus de zone « Problèmes à corriger » dans le calibrage.
Passer à « Correction complète » valide le lot courant après les contrôles habituels ; aucun bouton de validation séparé.
Les anciennes remarques déjà enregistrées restent conservées dans les dossiers.
La correction complète peut être importée en plusieurs réponses contenant des **copies complètes**.
Une copie illisible peut être déclarée dans `a_revoir`, sans inventer de points.

Les groupes et les copies à exclure restent accessibles pendant le calibrage, la correction
complète et les résultats. La notation par défaut est individuelle sur 20 ; l’option de groupe
Maths expertes est décrite plus bas. Les absences restent `ABS`.

## Validation et reprises

Les zones de réponse conservent leurs brouillons, y compris après redémarrage. L’import valide
et enregistre la réponse dans une transaction : un item invalide annule toute la réponse.
Le brouillon n’est effacé qu’après un import réussi. Les doubles clés JSON, `NaN`, les champs
inconnus et les réponses d’une ancienne révision sont rejetés.

Une copie non identifiée garde une référence `C001`, etc. Elle peut recevoir une fiche avec cette
référence et la mention « élève non identifié », puis être associée à un élève sans perdre sa
correction. Le CLI `calculate` conserve son exigence d’identification de toutes les copies.
Le numéro d’une copie déjà attribuée et corrigée ne peut pas être changé silencieusement.

Les consignes ne transmettent ni la liste de classe (noms, prénoms, numéros), ni les noms des
fichiers joints. L’IA repère les copies dans le PDF avec des références `C001`, etc. et
renvoie `numero: null`. L’enseignant associe les élèves dans le tableau local de prévisualisation
de l’inventaire, puis vérifie et valide. Les sélections envoyées pour correction ne contiennent
que les références, versions et pages, jamais l’identité locale. Cela n’anonymise pas les PDF :
les noms présents sur les copies jointes restent visibles pour l’IA.

Toutes les pages du paquet doivent être affectées exactement une fois, soit à une copie, soit
à `pages_ignorees` avec un motif. Les pages peuvent être non contiguës. Aucun élève manquant
n’est automatiquement déclaré absent. Le paquet source reste un seul fichier, jamais découpé.
Un dossier accepte un paquet ; pour le remplacer, créer un nouveau dossier.

Une nouvelle grille crée une révision et conserve l’ancien sujet et ses corrections. Les
références et pages des copies sont reprises, mais elles doivent être corrigées avec la nouvelle
grille. Modifier le corrigé de référence signale les corrections concernées « à revoir » et
annule la validation de l’échantillon. L’enseignant peut confirmer une correction existante
après vérification ou importer une correction mise à jour. Les rendus antérieurs sont marqués
« à régénérer ». Une compilation échouée ne publie pas de PDF partiel.

Un message Windows « Accès refusé » concerne les fichiers locaux et ne doit pas être envoyé
à l’IA pour réparation du JSON. Fermer les PDF ouverts puis réessayer ; si l’erreur persiste,
vérifier les droits du dossier de sortie et un éventuel verrouillage par sa synchronisation.
L’export réessaie brièvement les opérations de création, suppression et renommage bloquées.
Si le nettoyage du dossier temporaire échoue aussi, l’erreur initiale reste affichée. La demande
de réparation de format est réservée aux validations de réponses, avec une consigne et une
réponse non vides ; elle n’apparaît plus pour les erreurs de génération ou d’accès aux fichiers.

## Format à demander à l’IA

La consigne apparaît automatiquement. Cliquer sur **Copier**, l’envoyer dans l’IA avec les
PDF, puis coller le bloc JSON final à droite et utiliser le bouton d’import de l’étape.
Les discussions pédagogiques peuvent précéder ce bloc ; le texte collé dans l’application
doit contenir uniquement le JSON, éventuellement entouré de ses balises de bloc de code.

La consigne contient seulement le contrat utile à l’étape, le contexte pédagogique et les
références nécessaires. Les champs de correction partagent une définition commune avec le
validateur. Les commentaires et conseils sont du texte brut ; seuls les corrigés de référence
sont du LaTeX. L’anonymat est activé par défaut : `identite_lue` et `numero` restent `null`.
Si l’enseignant désactive l’anonymat, l’identité peut être lue sur la copie ; la liste de classe
n’est jamais transmise. Les calculs de notes restent locaux.

### Contrats historiques et compatibilité

Les sections suivantes décrivent les échanges séparés encore acceptés par les routes de
compatibilité. **Pour le parcours actuel, utiliser l’exemple complet affiché dans la consigne** :
le calibrage regroupe inventaire, corrigés et corrections dans une seule enveloppe. Les contrats
CLI restent décrits dans [correction_format.md](correction_format.md).

### Grille

L’enveloppe utilise la révision actuelle (0 avant la première validation). L’application l’incrémente
après validation. `validee` n’est pas autorisé : cette décision appartient au bouton enseignant.
Les exercices, questions et items suivent [le format d’évaluation](evaluation_format.md).

```json
{
  "dossier": "IDENTIFIANT_COPIE_DE_LA_CONSIGNE",
  "revision": 0,
  "versions": [{"version": "A"}],
  "grilles": [{
    "nom": "Équations", "version": "A",
    "exercices": [{"numero": "1", "questions": [{"numero": "1", "items": [
      {"code": "E1Q1I1", "description": "Résoudre l’équation", "bareme_max": 2,
       "regle_correction": "Appliquer les exigences discutées avec l’enseignant."},
      {"code": "E1Q1I2", "description": "Conclure", "bareme_max": 1}
    ]}]}]
  }]
}
```

Une grille commune utilise `version: null`. Chaque version doit avoir une grille compatible.
`sujet_latex` est facultatif dans `versions` : joindre le sujet PDF suffit pour ce parcours.
Les codes des items sont uniques dans leur grille, les numéros d’exercice/question sont des
chaînes. Les maxima sont des nombres ; le total d’une grille doit être strictement positif.

### Inventaire des copies

Exemple pour un paquet de trois pages et une grille déjà validée :

```json
{
  "dossier": "IDENTIFIANT_COPIE_DE_LA_CONSIGNE", "revision": 1,
  "copies": [
    {"reference": "C001", "numero": 1, "version": "A", "pages": [1]},
    {"reference": "C002", "numero": null, "version": "A", "pages": [2]}
  ],
  "pages_ignorees": [{"page": 3, "motif": "Page blanche"}],
  "absents": []
}
```

La pagination est physique, à partir de 1 dans le PDF du paquet. `numero` est l’ID global d’un
élève inscrit dans la classe ou `null`. `absents` contient les IDs explicitement déclarés absents.
Les anciennes réponses et brouillons utilisant des numéros de liste doivent être revérifiés et associés
aux IDs affichés dans le tableau local avant de les importer.
Les références `C001` à `C999999` sont stables dans le dossier.

### Corrigé de référence

Coller le **corps LaTeX**, sans enveloppe JSON, préambule, `documentclass` ni `begin/end{document}` :

```latex
\section*{Exercice 1}
\begin{align*}
2x+3 &= 7 \\
2x &= 4 \\
x &= 2
\end{align*}
Ainsi, $S=\{2\}$.
```

Il sera inclus dans les fiches de la version sélectionnée. Le bouton de vérification contrôle
le format général ; la syntaxe LaTeX est vérifiée lors de la compilation des fiches.
Le menu Corrigé dispose d’une grande zone de saisie redimensionnable ; l’aperçu du code n’est
plus plafonné en hauteur. Un corrigé enregistré est rechargé intégralement quand on revient
dans ce menu ; un brouillon en cours reste prioritaire. Aucun nombre de pages ni plafond de
caractères propre au corrigé n’est imposé. La protection générale des requêtes HTTP reste de
160 Mio (un dépassement est refusé, jamais tronqué). L’IA doit développer toutes les questions
et laisser LaTeX répartir le corrigé sur plusieurs pages, sans le condenser pour tenir sur une page.

### Corrections

```json
{
  "dossier": "IDENTIFIANT_COPIE_DE_LA_CONSIGNE", "revision": 1,
  "corrections": [{
    "reference": "C001",
    "items": [
      {"item_code": "E1Q1I1", "points_obtenus": 1, "statut": "partiel",
       "commentaire": "Une erreur de signe dans la dernière égalité.", "annotation": null},
      {"item_code": "E1Q1I2", "points_obtenus": 1, "statut": "acquis"}
    ],
    "annotations": [{"item_code": "E1Q1I1", "page": 1, "texte": "Vérifier le signe."}],
    "conseils": [{"item_code": "E1Q1I1", "texte": "Remplacer x par la solution trouvée pour la vérifier.", "priorite": 1}],
    "commentaire_global": "Méthode comprise ; soigner la vérification."
  }],
  "a_revoir": []
}
```

Tous les items de chaque copie doivent figurer exactement une fois. Les points sont des nombres
finis entre 0 et le maximum. Si le maximum n’est pas attribué, `commentaire` ou `annotation`
est obligatoire et non vide. Les statuts facultatifs sont `acquis`, `partiel`, `non_acquis`,
`non_repondu`. Les annotations sont liées aux items et à une page appartenant à cette copie.
Les coordonnées facultatives suivent [le contrat commun](correction_format.md).

Aucun total, `copie_id`, `grille_id` ou groupe n’est attendu de l’IA ici. L’application résout
les références puis appelle l’importeur commun. Pour corriger une réponse antérieure, fournir
de nouveau tous les items de la copie concernée. Les réponses acceptées restent dans l’historique
d’échanges SQL ; les tables de correction contiennent la dernière version validée.

Pour une écriture illisible, omettre cette copie de `corrections` et fournir
`"a_revoir": [{"reference": "C002", "motif": "Dernière ligne illisible"}]`.
Il ne faut ni inventer un score, ni traiter une copie incomplète comme un zéro.

### Consignes pour la prochaine fois

Après le document final (ou l’export final des sources), demander deux **textes complets de
remplacement**, basés sur les décisions réelles de la discussion. Recopier les identifiants
des consignes actives depuis le message généré ; `null` signifie qu’aucune version n’existe encore.

```json
{
  "dossier": "IDENTIFIANT_COPIE_DE_LA_CONSIGNE", "revision": 1,
  "base_generale": null, "base_classe": null,
  "generales": "Ne pas pénaliser deux fois une même erreur propagée, sauf règle explicite de la grille.",
  "classe": "Exiger une conclusion rédigée après la résolution."
}
```

Ces règles sont des **exemples**, pas des choix appliqués par défaut. L’enseignant compare la
proposition avec les textes actifs avant de remplacer. Les anciennes versions restent conservées.
Si une autre évaluation a déjà mis à jour les consignes, une proposition fondée sur l’ancienne
version est rejetée. Un dossier en cours garde les consignes de son démarrage ; seuls les nouveaux
dossiers prennent les nouveaux textes. Ne conserver ni noms, ni notes individuelles, ni règles
propres à un seul exercice dans les consignes durables.

## Données, sauvegarde et limites

Par défaut : base `db/smartcorrection.sqlite`, PDF et rendus sous `private/interface/`.
Sauvegarder **les deux**, application arrêtée. Les chemins de documents sont absolus : conserver
l’emplacement lors d’une restauration. Les données élèves et sorties sont ignorées par Git.

Au premier lancement, les Markdown de classe existants, dont `classes/TMEX.md`, sont importés
une fois dans les consignes SQLite. Ensuite, le parcours graphique lit et remplace ces consignes
dans l’application : il n’utilise plus les `.md` comme mémoire active. Les anciens fichiers et
l’option CLI `--classe-md` restent disponibles pour compatibilité. Les grilles lisibles continuent
d’être exportées en Markdown.

Le serveur écoute uniquement la boucle locale, vérifie l’origine des requêtes et exige un jeton
pour les écritures. Il sert uniquement les fichiers enregistrés sous son répertoire de données.
Le LaTeX doit rester un fragment de confiance ; [les précautions de compilation](../latex/README.md)
ne constituent pas un bac à sable complet.

Les annotations sont listées sur la fiche, pas dessinées sur le scan original. Les documents
joints à ce premier parcours doivent être des PDF. Les variantes de notation et groupes restent
accessibles dans le moteur CLI. Les tests utilisent des évaluations **fictives** : la relecture
d’un paquet réel, du rendu et du parcours Windows reste une étape de validation enseignant.

### Exclure une copie du document final

Dans **Corriger le reste → Suivi du paquet**, décochez la case **Document final**
de la copie concernée. Le choix est enregistré immédiatement. La copie reste visible
avec la mention **Exclue** ; recochez-la pour la réinclure.

Le PDF final, les fiches individuelles, les sources LaTeX et les lignes de notes CSV/JSON
ne contiennent que les copies incluses. Le JSON conserve aussi la liste des références
exclues (`copies_exclues`). Une copie exclue non corrigée ou à revoir ne bloque plus
le rendu des autres. Au moins une copie doit rester incluse.

La correction, les annotations, les conseils et le statut de présence sont conservés.
Ce choix ne change pas l’échantillon de test. La consigne **Corriger le reste** ne demande
plus les copies exclues ; leur réactivation les remet dans les copies à traiter si nécessaire.
Chaque changement signale les documents finaux précédents **à régénérer**.

En mode groupe, l’exclusion concerne les documents, pas le barème : une note valide
reste utilisée pour les camarades. Une correction manquante ou à revoir laisse leur
note de groupe en attente. Exclure une fiche ne déclare jamais l’élève absent.

### Note de groupe Maths expertes

Dans **Repérer les copies**, ouvrir **Note de groupe · Maths expertes** après avoir enregistré la grille.
Le même panneau est accessible dans **Tester la correction** et **Corriger le reste**.
L’option est désactivée par défaut. Cocher **Activer la note de groupe**, coller une ligne d’IDs
par groupe (`2, 31, 3, 22`), puis **Enregistrer les groupes**. Le tableau affiche les identités locales ;
les doublons et numéros inconnus sont refusés sans modifier les groupes enregistrés. Les élèves
sans groupe sont signalés. Les groupes ne sont jamais ajoutés aux consignes IA.

La note individuelle est convertie sur 15 ; la moyenne des **autres membres** est convertie sur 5.
La finale est leur somme sur 20, arrondie au demi-point comme dans le moteur existant. Les absents
sont exclus de la moyenne. Une copie non corrigée, non repérée ou à revoir laisse la part groupe
et la finale en attente. Sans camarade disponible ou sans identité/groupe, elles restent « À traiter ».
Le test sur cinq copies utilise aussi les camarades hors échantillon, sans inventer leurs notes.

Les fiches A5 paysage conservent correction à gauche et corrigé à droite. En mode groupe, le tableau
comporte individuel /15, groupe /5 (détail des camarades en petit) et finale /20. Les exports CSV/JSON
contiennent ces notes ; `etat_groupe` explique les notes vides. Un document final peut contenir des cas
« À traiter » : document produit ne signifie pas que toutes les notes sont calculables.

Changer les groupes ou une correction invalide les anciens PDF. Régénérer les fiches recalcule les
notes depuis SQLite. Changer de grille conserve les groupes ; désactiver l’option conserve leur saisie
et revient à la notation individuelle sur 20.

### Lecture des échanges

Les deux zones restent visibles : **Consigne à copier dans l’IA**, avec **Copier** en dessous, et **Résultat de l’IA**. Après **Vérifier**, **Enregistrer et continuer** enregistre la grille, le corrigé ou l’inventaire et ouvre la suite. Les versions de corrigé manquantes sont proposées successivement.

Pour les corrections, **Enregistrer les corrections** reste sur la page afin de relire les fiches ou d’importer une autre réponse. **Voir les fiches du test** ouvre le PDF ; passer à l’étape suivante valide ensuite l’échantillon. **Créer le PDF final** produit le rendu complet. Les sources LaTeX et les documents précédents sont dans **Plus d’options**.

### Deux niveaux de grille

La grille détaillée par item reste la référence pour l’IA, SQLite et les calculs. Le JSON
de correction conserve chaque item et ses points. La fiche élève affiche un **bilan par question** :
somme des points / barème de la question, puis seulement les erreurs des items ayant perdu des
points. Les retours identiques sont affichés une seule fois par question ; les critères et les
commentaires sur les items entièrement réussis ne sont pas répétés. Une question réussie
conserve sa note, avec une case d’erreurs vide. Les données détaillées et les exports JSON
restent inchangés ; les totaux des questions ne recalculent pas la note finale.

### Validation, affectations et note

« Valider et voir le barème » enregistre le barème et ouvre immédiatement son aperçu PDF.
L’écran 1 reste affiché ; passer ensuite au calibrage avec « Étape suivante ».
Les suggestions d’affectation proposent uniquement les élèves non encore attribués dans le dossier.
Retirer une affectation remet l’élève dans la liste. L’identité actuellement affectée reste affichée.
Dans le PDF, la note est agrandie à 14 points et entourée d’un cadre bleu. La mention
« Note provisoire » reste visible lorsque des vérifications sont nécessaires.

### Choix de grille et copies originales

Dans la mise en page, choisir « Grille par question » (par défaut) ou « Grille détaillée ».
Le second mode affiche le titre d’exercice, celui de la question et les libellés des items,
avec des polices et retraits distincts. Les codes et règles internes ne sont jamais imprimés.
Changer ce réglage marque les PDF à régénérer, sans changer la correction enregistrée.

Le tableau des copies incluses affiche leurs notes actuelles, calculées localement ; une copie
non corrigée reste sans note. Les absences et notes de groupe en attente sont signalées.

Importer le PDF du paquet sur le premier écran. En calibrage, l’aperçu intercale les pages de
chaque copie avec sa fiche de correction. Sans PDF importé, seules les fiches sont affichées.
À la fin, deux téléchargements sont proposés si le paquet est disponible : « Corrections seules »
et « Copies et corrections intercalées ». Les pages conservent leur taille d’origine ; une fiche
A5 et une copie A4 peuvent donc coexister. Seules les copies sélectionnées sont intercalées,
sans pages ignorées ; les absences ont une fiche sans pages de copie.
