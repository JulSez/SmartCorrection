PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS eleve (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT,
    prenom TEXT
);
CREATE TABLE IF NOT EXISTS eleve_classe (
    eleve_id INTEGER NOT NULL REFERENCES eleve(id),
    classe TEXT NOT NULL,
    numero INTEGER NOT NULL CHECK(numero>0),
    PRIMARY KEY(eleve_id,classe), UNIQUE(classe,numero)
);
CREATE VIEW IF NOT EXISTS eleve_par_classe AS
    SELECT e.id,e.nom,e.prenom,c.classe,c.numero FROM eleve e JOIN eleve_classe c ON c.eleve_id=e.id;
CREATE TABLE IF NOT EXISTS eleve_nom_importe (
    eleve_id INTEGER NOT NULL REFERENCES eleve(id), nom TEXT NOT NULL, prenom TEXT NOT NULL,
    PRIMARY KEY(eleve_id,nom,prenom)
);
CREATE TABLE IF NOT EXISTS eleve_fusion (
    ancien_id INTEGER PRIMARY KEY, eleve_id INTEGER NOT NULL REFERENCES eleve(id),
    nom TEXT, prenom TEXT, cree_le TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sujet (
    id INTEGER PRIMARY KEY,
    classe TEXT NOT NULL,
    chapitres TEXT,
    type TEXT,
    titre TEXT,
    date_evaluation TEXT,
    config_notes TEXT
);

CREATE TABLE IF NOT EXISTS version (
    id INTEGER PRIMARY KEY,
    sujet_id INTEGER NOT NULL REFERENCES sujet(id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    str_latex TEXT NOT NULL,
    UNIQUE(sujet_id, version)
);

CREATE TABLE IF NOT EXISTS corrige (
    id INTEGER PRIMARY KEY,
    version_id INTEGER NOT NULL REFERENCES version(id) ON DELETE CASCADE,
    str_latex TEXT NOT NULL,
    UNIQUE(version_id)
);

CREATE TABLE IF NOT EXISTS copie (
    id INTEGER PRIMARY KEY,
    eleve_id INTEGER REFERENCES eleve(id),
    sujet_id INTEGER NOT NULL REFERENCES sujet(id),
    version_id INTEGER REFERENCES version(id),
    pdf_path TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'present' CHECK(statut IN ('present', 'absent'))
);

CREATE TABLE IF NOT EXISTS grille (
    id INTEGER PRIMARY KEY,
    sujet_id INTEGER NOT NULL REFERENCES sujet(id) ON DELETE CASCADE,
    version_id INTEGER REFERENCES version(id),
    nom TEXT,
    total_points REAL,
    valide INTEGER NOT NULL DEFAULT 0 CHECK(valide IN (0, 1))
);

CREATE TABLE IF NOT EXISTS exercice (
    id INTEGER PRIMARY KEY,
    grille_id INTEGER NOT NULL REFERENCES grille(id) ON DELETE CASCADE,
    numero TEXT NOT NULL,
    titre TEXT,
    ordre INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS question (
    id INTEGER PRIMARY KEY,
    exercice_id INTEGER NOT NULL REFERENCES exercice(id) ON DELETE CASCADE,
    numero TEXT NOT NULL,
    texte TEXT,
    ordre INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS item (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES question(id) ON DELETE CASCADE,
    grille_id INTEGER NOT NULL REFERENCES grille(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    description TEXT NOT NULL,
    bareme_max REAL NOT NULL,
    ordre INTEGER NOT NULL,
    regle_correction TEXT,
    UNIQUE(grille_id, code)
);

CREATE TABLE IF NOT EXISTS correction (
    id INTEGER PRIMARY KEY,
    copie_id INTEGER NOT NULL REFERENCES copie(id) ON DELETE CASCADE,
    grille_id INTEGER NOT NULL REFERENCES grille(id),
    note_brute REAL,
    note_finale REAL,
    commentaire_global TEXT,
    UNIQUE(copie_id)
);

CREATE TABLE IF NOT EXISTS correction_item (
    id INTEGER PRIMARY KEY,
    correction_id INTEGER NOT NULL REFERENCES correction(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES item(id),
    points_obtenus REAL NOT NULL,
    statut TEXT,
    annotation TEXT,
    commentaire TEXT,
    UNIQUE(correction_id, item_id)
);

CREATE TABLE IF NOT EXISTS conseil (
    id INTEGER PRIMARY KEY,
    correction_id INTEGER NOT NULL REFERENCES correction(id) ON DELETE CASCADE,
    item_id INTEGER REFERENCES item(id),
    texte TEXT NOT NULL,
    priorite INTEGER
);

CREATE TABLE IF NOT EXISTS annotation (
    id INTEGER PRIMARY KEY,
    correction_id INTEGER NOT NULL REFERENCES correction(id) ON DELETE CASCADE,
    item_id INTEGER REFERENCES item(id),
    page INTEGER NOT NULL,
    x REAL,
    y REAL,
    largeur REAL,
    hauteur REAL,
    texte TEXT NOT NULL,
    type_annotation TEXT
);

CREATE TABLE IF NOT EXISTS groupe (
    id INTEGER PRIMARY KEY,
    sujet_id INTEGER NOT NULL REFERENCES sujet(id) ON DELETE CASCADE,
    numero_groupe INTEGER
);

CREATE TABLE IF NOT EXISTS groupe_eleve (
    groupe_id INTEGER NOT NULL REFERENCES groupe(id) ON DELETE CASCADE,
    eleve_id INTEGER NOT NULL REFERENCES eleve(id),
    PRIMARY KEY (groupe_id, eleve_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS copie_unique ON copie(sujet_id, eleve_id);
CREATE UNIQUE INDEX IF NOT EXISTS groupe_numero ON groupe(sujet_id, numero_groupe);
CREATE UNIQUE INDEX IF NOT EXISTS grille_version ON grille(sujet_id, COALESCE(version_id, 0));
CREATE UNIQUE INDEX IF NOT EXISTS exercice_numero ON exercice(grille_id, numero);
CREATE UNIQUE INDEX IF NOT EXISTS question_numero ON question(exercice_id, numero);
CREATE INDEX IF NOT EXISTS correction_item_item ON correction_item(item_id);
CREATE INDEX IF NOT EXISTS groupe_eleve_eleve ON groupe_eleve(eleve_id);

CREATE TRIGGER IF NOT EXISTS validate_copie_insert BEFORE INSERT ON copie
WHEN NEW.statut NOT IN ('present','absent') OR (NEW.eleve_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM eleve_classe e JOIN sujet s ON s.classe=e.classe WHERE e.eleve_id=NEW.eleve_id AND s.id=NEW.sujet_id)) OR (NEW.version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM version WHERE id=NEW.version_id AND sujet_id=NEW.sujet_id))
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: copie'); END;

CREATE TRIGGER IF NOT EXISTS validate_copie_update BEFORE UPDATE ON copie
WHEN NEW.statut NOT IN ('present','absent') OR (NEW.eleve_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM eleve_classe e JOIN sujet s ON s.classe=e.classe WHERE e.eleve_id=NEW.eleve_id AND s.id=NEW.sujet_id)) OR (NEW.version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM version WHERE id=NEW.version_id AND sujet_id=NEW.sujet_id))
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: copie'); END;

CREATE TRIGGER IF NOT EXISTS validate_grille_insert BEFORE INSERT ON grille
WHEN NEW.valide NOT IN (0,1) OR (NEW.version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM version WHERE id=NEW.version_id AND sujet_id=NEW.sujet_id))
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: grille'); END;

CREATE TRIGGER IF NOT EXISTS validate_grille_update BEFORE UPDATE ON grille
WHEN NEW.valide NOT IN (0,1) OR (NEW.version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM version WHERE id=NEW.version_id AND sujet_id=NEW.sujet_id))
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: grille'); END;

CREATE TRIGGER IF NOT EXISTS validate_item_insert BEFORE INSERT ON item
WHEN NEW.bareme_max < 0 OR NEW.bareme_max > 1e308 OR NOT EXISTS (SELECT 1 FROM question q JOIN exercice e ON e.id=q.exercice_id WHERE q.id=NEW.question_id AND e.grille_id=NEW.grille_id)
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: item'); END;

CREATE TRIGGER IF NOT EXISTS validate_item_update BEFORE UPDATE ON item
WHEN NEW.bareme_max < 0 OR NEW.bareme_max > 1e308 OR NOT EXISTS (SELECT 1 FROM question q JOIN exercice e ON e.id=q.exercice_id WHERE q.id=NEW.question_id AND e.grille_id=NEW.grille_id)
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: item'); END;

CREATE TRIGGER IF NOT EXISTS validate_correction_insert BEFORE INSERT ON correction
WHEN NOT EXISTS (SELECT 1 FROM copie c JOIN grille g ON g.sujet_id=c.sujet_id WHERE c.id=NEW.copie_id AND c.statut='present' AND g.id=NEW.grille_id AND g.valide=1 AND (g.version_id IS NULL OR g.version_id=c.version_id))
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: correction'); END;

CREATE TRIGGER IF NOT EXISTS validate_correction_update BEFORE UPDATE ON correction
WHEN NOT EXISTS (SELECT 1 FROM copie c JOIN grille g ON g.sujet_id=c.sujet_id WHERE c.id=NEW.copie_id AND c.statut='present' AND g.id=NEW.grille_id AND g.valide=1 AND (g.version_id IS NULL OR g.version_id=c.version_id))
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: correction'); END;

CREATE TRIGGER IF NOT EXISTS validate_correction_item_insert BEFORE INSERT ON correction_item
WHEN NEW.points_obtenus < 0 OR NEW.points_obtenus > 1e308 OR NOT EXISTS (SELECT 1 FROM item i JOIN correction c ON c.grille_id=i.grille_id WHERE i.id=NEW.item_id AND c.id=NEW.correction_id AND NEW.points_obtenus <= i.bareme_max)
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: correction_item'); END;

CREATE TRIGGER IF NOT EXISTS validate_correction_item_update BEFORE UPDATE ON correction_item
WHEN NEW.points_obtenus < 0 OR NEW.points_obtenus > 1e308 OR NOT EXISTS (SELECT 1 FROM item i JOIN correction c ON c.grille_id=i.grille_id WHERE i.id=NEW.item_id AND c.id=NEW.correction_id AND NEW.points_obtenus <= i.bareme_max)
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: correction_item'); END;

CREATE TRIGGER IF NOT EXISTS validate_conseil_insert BEFORE INSERT ON conseil
WHEN NEW.item_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM item i JOIN correction c ON c.grille_id=i.grille_id WHERE i.id=NEW.item_id AND c.id=NEW.correction_id)
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: conseil'); END;

CREATE TRIGGER IF NOT EXISTS validate_conseil_update BEFORE UPDATE ON conseil
WHEN NEW.item_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM item i JOIN correction c ON c.grille_id=i.grille_id WHERE i.id=NEW.item_id AND c.id=NEW.correction_id)
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: conseil'); END;

CREATE TRIGGER IF NOT EXISTS validate_annotation_insert BEFORE INSERT ON annotation
WHEN NEW.page < 1 OR NEW.item_id IS NULL OR NOT EXISTS (SELECT 1 FROM item i JOIN correction c ON c.grille_id=i.grille_id WHERE i.id=NEW.item_id AND c.id=NEW.correction_id) OR NEW.x < 0 OR NEW.y < 0 OR NEW.largeur < 0 OR NEW.hauteur < 0 OR NEW.x > 1 OR NEW.y > 1 OR NEW.x+COALESCE(NEW.largeur,0)>1 OR NEW.y+COALESCE(NEW.hauteur,0)>1
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: annotation'); END;

CREATE TRIGGER IF NOT EXISTS validate_annotation_update BEFORE UPDATE ON annotation
WHEN NEW.page < 1 OR NEW.item_id IS NULL OR NOT EXISTS (SELECT 1 FROM item i JOIN correction c ON c.grille_id=i.grille_id WHERE i.id=NEW.item_id AND c.id=NEW.correction_id) OR NEW.x < 0 OR NEW.y < 0 OR NEW.largeur < 0 OR NEW.hauteur < 0 OR NEW.x > 1 OR NEW.y > 1 OR NEW.x+COALESCE(NEW.largeur,0)>1 OR NEW.y+COALESCE(NEW.hauteur,0)>1
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: annotation'); END;

CREATE TRIGGER IF NOT EXISTS validate_groupe_eleve_insert BEFORE INSERT ON groupe_eleve
WHEN NOT EXISTS (SELECT 1 FROM groupe g JOIN sujet s ON s.id=g.sujet_id JOIN eleve_classe e ON e.classe=s.classe WHERE g.id=NEW.groupe_id AND e.eleve_id=NEW.eleve_id) OR EXISTS (SELECT 1 FROM groupe_eleve ge JOIN groupe g ON g.id=ge.groupe_id JOIN groupe target ON target.sujet_id=g.sujet_id WHERE target.id=NEW.groupe_id AND ge.eleve_id=NEW.eleve_id AND ge.groupe_id<>NEW.groupe_id)
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: groupe_eleve'); END;

CREATE TRIGGER IF NOT EXISTS validate_groupe_eleve_update BEFORE UPDATE ON groupe_eleve
WHEN NOT EXISTS (SELECT 1 FROM groupe g JOIN sujet s ON s.id=g.sujet_id JOIN eleve_classe e ON e.classe=s.classe WHERE g.id=NEW.groupe_id AND e.eleve_id=NEW.eleve_id) OR EXISTS (SELECT 1 FROM groupe_eleve ge JOIN groupe g ON g.id=ge.groupe_id JOIN groupe target ON target.sujet_id=g.sujet_id WHERE target.id=NEW.groupe_id AND ge.eleve_id=NEW.eleve_id AND ge.groupe_id<>NEW.groupe_id)
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: groupe_eleve'); END;

CREATE TRIGGER IF NOT EXISTS freeze_item_update BEFORE UPDATE ON item
WHEN EXISTS (SELECT 1 FROM correction WHERE grille_id=OLD.grille_id)
BEGIN SELECT RAISE(ABORT, 'Barème déjà utilisé: créer une nouvelle évaluation'); END;

CREATE TRIGGER IF NOT EXISTS freeze_item_delete BEFORE DELETE ON item
WHEN EXISTS (SELECT 1 FROM correction WHERE grille_id=OLD.grille_id)
BEGIN SELECT RAISE(ABORT, 'Barème déjà utilisé: créer une nouvelle évaluation'); END;

CREATE TRIGGER IF NOT EXISTS freeze_question_update BEFORE UPDATE ON question
WHEN EXISTS (SELECT 1 FROM exercice e JOIN correction c ON c.grille_id=e.grille_id WHERE e.id=OLD.exercice_id)
BEGIN SELECT RAISE(ABORT, 'Barème déjà utilisé: créer une nouvelle évaluation'); END;

CREATE TRIGGER IF NOT EXISTS freeze_question_delete BEFORE DELETE ON question
WHEN EXISTS (SELECT 1 FROM exercice e JOIN correction c ON c.grille_id=e.grille_id WHERE e.id=OLD.exercice_id)
BEGIN SELECT RAISE(ABORT, 'Barème déjà utilisé: créer une nouvelle évaluation'); END;

CREATE TRIGGER IF NOT EXISTS freeze_exercice_update BEFORE UPDATE ON exercice
WHEN EXISTS (SELECT 1 FROM correction WHERE grille_id=OLD.grille_id)
BEGIN SELECT RAISE(ABORT, 'Barème déjà utilisé: créer une nouvelle évaluation'); END;

CREATE TRIGGER IF NOT EXISTS freeze_exercice_delete BEFORE DELETE ON exercice
WHEN EXISTS (SELECT 1 FROM correction WHERE grille_id=OLD.grille_id)
BEGIN SELECT RAISE(ABORT, 'Barème déjà utilisé: créer une nouvelle évaluation'); END;

CREATE TRIGGER IF NOT EXISTS freeze_grille_update BEFORE UPDATE ON grille
WHEN EXISTS (SELECT 1 FROM correction WHERE grille_id=OLD.id) AND (NEW.sujet_id IS NOT OLD.sujet_id OR NEW.version_id IS NOT OLD.version_id OR NEW.total_points IS NOT OLD.total_points OR NEW.nom IS NOT OLD.nom OR NEW.valide < OLD.valide)
BEGIN SELECT RAISE(ABORT, 'Barème déjà utilisé: créer une nouvelle évaluation'); END;

CREATE TRIGGER IF NOT EXISTS freeze_grille_delete BEFORE DELETE ON grille
WHEN EXISTS (SELECT 1 FROM correction WHERE grille_id=OLD.id)
BEGIN SELECT RAISE(ABORT, 'Barème déjà utilisé: créer une nouvelle évaluation'); END;

CREATE TABLE IF NOT EXISTS evaluation_import (
 cle TEXT PRIMARY KEY,
 empreinte TEXT NOT NULL,
 sujet_id INTEGER NOT NULL UNIQUE REFERENCES sujet(id) ON DELETE CASCADE
);

CREATE TRIGGER IF NOT EXISTS freeze_item_insert BEFORE INSERT ON item
WHEN EXISTS (SELECT 1 FROM correction WHERE grille_id=NEW.grille_id)
BEGIN SELECT RAISE(ABORT, 'Barème déjà utilisé'); END;

CREATE TRIGGER IF NOT EXISTS freeze_exercice_insert BEFORE INSERT ON exercice
WHEN EXISTS (SELECT 1 FROM correction WHERE grille_id=NEW.grille_id)
BEGIN SELECT RAISE(ABORT, 'Barème déjà utilisé'); END;

CREATE TRIGGER IF NOT EXISTS freeze_question_insert BEFORE INSERT ON question
WHEN EXISTS (SELECT 1 FROM exercice e JOIN correction c ON c.grille_id=e.grille_id WHERE e.id=NEW.exercice_id)
BEGIN SELECT RAISE(ABORT, 'Barème déjà utilisé'); END;

CREATE TRIGGER IF NOT EXISTS freeze_version_identity BEFORE UPDATE OF sujet_id ON version
WHEN NEW.sujet_id IS NOT OLD.sujet_id AND (EXISTS(SELECT 1 FROM copie WHERE version_id=OLD.id) OR EXISTS(SELECT 1 FROM grille WHERE version_id=OLD.id))
BEGIN SELECT RAISE(ABORT, 'Version utilisée'); END;
CREATE TRIGGER IF NOT EXISTS freeze_copy_identity BEFORE UPDATE ON copie
WHEN EXISTS(SELECT 1 FROM correction WHERE copie_id=OLD.id) AND
 (NEW.sujet_id IS NOT OLD.sujet_id OR NEW.version_id IS NOT OLD.version_id OR (OLD.eleve_id IS NOT NULL AND NEW.eleve_id IS NOT NULL AND NEW.eleve_id IS NOT OLD.eleve_id) OR NEW.statut IS NOT OLD.statut)
BEGIN SELECT RAISE(ABORT, 'Identité de copie déjà corrigée'); END;
CREATE TRIGGER IF NOT EXISTS freeze_membership_delete BEFORE DELETE ON eleve_classe
WHEN EXISTS(SELECT 1 FROM copie c JOIN sujet s ON s.id=c.sujet_id WHERE c.eleve_id=OLD.eleve_id AND s.classe=OLD.classe)
 OR EXISTS(SELECT 1 FROM groupe_eleve ge JOIN groupe g ON g.id=ge.groupe_id JOIN sujet s ON s.id=g.sujet_id WHERE ge.eleve_id=OLD.eleve_id AND s.classe=OLD.classe)
BEGIN SELECT RAISE(ABORT, 'Inscription utilisée'); END;
CREATE TRIGGER IF NOT EXISTS freeze_membership_update BEFORE UPDATE ON eleve_classe
WHEN NEW.eleve_id IS NOT OLD.eleve_id OR NEW.classe IS NOT OLD.classe
BEGIN SELECT RAISE(ABORT, 'Identité d’inscription immuable'); END;
CREATE TRIGGER IF NOT EXISTS freeze_pupil_id BEFORE UPDATE OF id ON eleve
WHEN NEW.id IS NOT OLD.id
BEGIN SELECT RAISE(ABORT, 'ID élève immuable'); END;
CREATE TRIGGER IF NOT EXISTS freeze_subject_class BEFORE UPDATE OF classe ON sujet
WHEN NEW.classe IS NOT OLD.classe AND (EXISTS(SELECT 1 FROM copie WHERE sujet_id=OLD.id) OR EXISTS(SELECT 1 FROM groupe WHERE sujet_id=OLD.id))
BEGIN SELECT RAISE(ABORT, 'Classe de sujet utilisée'); END;
CREATE TRIGGER IF NOT EXISTS freeze_group_subject BEFORE UPDATE OF sujet_id ON groupe
WHEN NEW.sujet_id IS NOT OLD.sujet_id AND EXISTS(SELECT 1 FROM groupe_eleve WHERE groupe_id=OLD.id)
BEGIN SELECT RAISE(ABORT, 'Groupe utilisé'); END;

