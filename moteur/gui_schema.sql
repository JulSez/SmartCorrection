-- Interface: drafts are exchange documents; validated educational data remains relational.
CREATE TABLE IF NOT EXISTS ui_meta (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS consigne_revision (
 id INTEGER PRIMARY KEY, portee TEXT NOT NULL CHECK(portee IN ('generale','classe')),
 classe TEXT NOT NULL DEFAULT '', texte TEXT NOT NULL, source_dossier TEXT,
 cree_le TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS consigne_active (
 portee TEXT NOT NULL, classe TEXT NOT NULL DEFAULT '',
 revision_id INTEGER NOT NULL REFERENCES consigne_revision(id), PRIMARY KEY(portee,classe)
);
CREATE TABLE IF NOT EXISTS ui_dossier (
 id TEXT PRIMARY KEY, classe TEXT NOT NULL, titre TEXT NOT NULL,
 sujet_id INTEGER REFERENCES sujet(id), revision INTEGER NOT NULL DEFAULT 0,
 generale_id INTEGER REFERENCES consigne_revision(id), classe_id INTEGER REFERENCES consigne_revision(id),
 echantillon_valide INTEGER NOT NULL DEFAULT 0, termine INTEGER NOT NULL DEFAULT 0,
 cree_le TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ui_revision (
 dossier_id TEXT NOT NULL REFERENCES ui_dossier(id), revision INTEGER NOT NULL,
 sujet_id INTEGER NOT NULL REFERENCES sujet(id), PRIMARY KEY(dossier_id,revision)
);
CREATE TABLE IF NOT EXISTS ui_fichier (
 id TEXT PRIMARY KEY, dossier_id TEXT NOT NULL REFERENCES ui_dossier(id),
 role TEXT NOT NULL CHECK(role IN ('paquet','sujet','corrige','cours','modele')),
 nom TEXT NOT NULL, chemin TEXT NOT NULL, pages INTEGER NOT NULL, empreinte TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ui_paquet_unique ON ui_fichier(dossier_id) WHERE role='paquet';
CREATE TABLE IF NOT EXISTS ui_copie (
 dossier_id TEXT NOT NULL REFERENCES ui_dossier(id), reference TEXT NOT NULL,
 copie_id INTEGER NOT NULL UNIQUE REFERENCES copie(id), echantillon INTEGER NOT NULL DEFAULT 0,
 a_revoir TEXT, PRIMARY KEY(dossier_id,reference)
);
-- A rendering choice, independent of attendance, marks and sample membership.
CREATE TABLE IF NOT EXISTS ui_copie_exclue (
 dossier_id TEXT NOT NULL, reference TEXT NOT NULL,
 PRIMARY KEY(dossier_id,reference),
 FOREIGN KEY(dossier_id,reference) REFERENCES ui_copie(dossier_id,reference) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS ui_page_ignoree (
 dossier_id TEXT NOT NULL REFERENCES ui_dossier(id), page INTEGER NOT NULL CHECK(page>0),
 motif TEXT NOT NULL, PRIMARY KEY(dossier_id,page)
);
CREATE TABLE IF NOT EXISTS ui_verification (
 copie_id INTEGER NOT NULL REFERENCES copie(id) ON DELETE CASCADE,
 ordre INTEGER NOT NULL CHECK(ordre>0), texte TEXT NOT NULL,
 PRIMARY KEY(copie_id,ordre)
);
CREATE TABLE IF NOT EXISTS ui_brouillon (
 dossier_id TEXT NOT NULL REFERENCES ui_dossier(id), etape TEXT NOT NULL, texte TEXT NOT NULL,
 PRIMARY KEY(dossier_id,etape)
);
CREATE TABLE IF NOT EXISTS ui_echange (
 id INTEGER PRIMARY KEY, dossier_id TEXT NOT NULL REFERENCES ui_dossier(id),
 revision INTEGER NOT NULL, etape TEXT NOT NULL, texte TEXT NOT NULL,
 cree_le TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ui_rendu (
 id TEXT PRIMARY KEY, dossier_id TEXT NOT NULL REFERENCES ui_dossier(id), revision INTEGER NOT NULL,
 final INTEGER NOT NULL, chemin TEXT NOT NULL, valide INTEGER NOT NULL DEFAULT 1,
 cree_le TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
