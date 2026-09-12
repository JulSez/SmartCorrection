PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS eleve (
    id INTEGER PRIMARY KEY,
    classe TEXT NOT NULL,
    numero INTEGER NOT NULL,
    nom TEXT,
    prenom TEXT,
    UNIQUE(classe, numero)
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
    eleve_id INTEGER NOT NULL REFERENCES eleve(id),
    sujet_id INTEGER NOT NULL REFERENCES sujet(id),
    version_id INTEGER REFERENCES version(id),
    pdf_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS grille (
    id INTEGER PRIMARY KEY,
    sujet_id INTEGER NOT NULL REFERENCES sujet(id) ON DELETE CASCADE,
    version_id INTEGER REFERENCES version(id),
    nom TEXT,
    total_points REAL
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
    code TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    bareme_max REAL NOT NULL,
    ordre INTEGER NOT NULL,
    regle_correction TEXT
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
