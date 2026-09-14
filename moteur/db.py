from __future__ import annotations
import sqlite3
import uuid
import json
import re
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path('db/smartcorrection.sqlite')
SCHEMA = Path(__file__).with_name('schema.sql')
SCHEMA_VERSION = 6

V3_SCHEMA = r'''
CREATE TABLE IF NOT EXISTS copie_page (
    copie_id INTEGER NOT NULL REFERENCES copie(id) ON DELETE CASCADE,
    page INTEGER NOT NULL CHECK(page > 0),
    ordre INTEGER NOT NULL CHECK(ordre > 0),
    PRIMARY KEY (copie_id, page),
    UNIQUE (copie_id, ordre)
);
CREATE INDEX IF NOT EXISTS copie_page_page ON copie_page(page);

CREATE TRIGGER IF NOT EXISTS validate_copie_page_insert BEFORE INSERT ON copie_page
WHEN NOT EXISTS (SELECT 1 FROM copie WHERE id=NEW.copie_id)
 OR EXISTS (
    SELECT 1 FROM copie_page cp
    JOIN copie source ON source.id=cp.copie_id
    JOIN copie target ON target.id=NEW.copie_id
    WHERE cp.page=NEW.page
      AND source.sujet_id=target.sujet_id
      AND source.pdf_path=target.pdf_path
      AND source.pdf_path<>''
      AND cp.copie_id<>NEW.copie_id
 )
BEGIN SELECT RAISE(ABORT, 'Page PDF déjà affectée à une autre copie'); END;

CREATE TRIGGER IF NOT EXISTS validate_copie_page_update BEFORE UPDATE ON copie_page
WHEN NOT EXISTS (SELECT 1 FROM copie WHERE id=NEW.copie_id)
 OR EXISTS (
    SELECT 1 FROM copie_page cp
    JOIN copie source ON source.id=cp.copie_id
    JOIN copie target ON target.id=NEW.copie_id
    WHERE cp.page=NEW.page
      AND source.sujet_id=target.sujet_id
      AND source.pdf_path=target.pdf_path
      AND source.pdf_path<>''
      AND cp.copie_id<>NEW.copie_id
 )
BEGIN SELECT RAISE(ABORT, 'Page PDF déjà affectée à une autre copie'); END;

CREATE TRIGGER IF NOT EXISTS freeze_copie_page_insert BEFORE INSERT ON copie_page
WHEN EXISTS(SELECT 1 FROM correction WHERE copie_id=NEW.copie_id)
BEGIN SELECT RAISE(ABORT, 'Pages de copie déjà corrigée'); END;
CREATE TRIGGER IF NOT EXISTS freeze_copie_page_update BEFORE UPDATE ON copie_page
WHEN EXISTS(SELECT 1 FROM correction WHERE copie_id=OLD.copie_id)
BEGIN SELECT RAISE(ABORT, 'Pages de copie déjà corrigée'); END;
CREATE TRIGGER IF NOT EXISTS freeze_copie_page_delete BEFORE DELETE ON copie_page
WHEN EXISTS(SELECT 1 FROM correction WHERE copie_id=OLD.copie_id)
BEGIN SELECT RAISE(ABORT, 'Pages de copie déjà corrigée'); END;
CREATE TRIGGER IF NOT EXISTS freeze_copy_pdf BEFORE UPDATE OF pdf_path ON copie
WHEN NEW.pdf_path IS NOT OLD.pdf_path AND EXISTS(SELECT 1 FROM correction WHERE copie_id=OLD.id)
BEGIN SELECT RAISE(ABORT, 'PDF de copie déjà corrigée'); END;
'''

V4_SCHEMA = r'''
DROP INDEX IF EXISTS copie_unique;
DROP TRIGGER IF EXISTS validate_copie_insert;
DROP TRIGGER IF EXISTS validate_copie_update;
DROP TRIGGER IF EXISTS validate_correction_insert;
DROP TRIGGER IF EXISTS validate_correction_update;
DROP TRIGGER IF EXISTS freeze_version_identity;
DROP TRIGGER IF EXISTS freeze_copy_identity;
DROP TRIGGER IF EXISTS freeze_copy_pdf;
DROP TRIGGER IF EXISTS freeze_pupil_class;
DROP TRIGGER IF EXISTS freeze_subject_class;
DROP TRIGGER IF EXISTS validate_copie_page_insert;
DROP TRIGGER IF EXISTS validate_copie_page_update;
DROP TRIGGER IF EXISTS freeze_copie_page_insert;
DROP TRIGGER IF EXISTS freeze_copie_page_update;
DROP TRIGGER IF EXISTS freeze_copie_page_delete;

CREATE TABLE copie_v4 (
    id INTEGER PRIMARY KEY,
    eleve_id INTEGER REFERENCES eleve(id),
    sujet_id INTEGER NOT NULL REFERENCES sujet(id),
    version_id INTEGER REFERENCES version(id),
    pdf_path TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'present' CHECK(statut IN ('present', 'absent'))
);
INSERT INTO copie_v4(id,eleve_id,sujet_id,version_id,pdf_path,statut)
SELECT id,eleve_id,sujet_id,version_id,pdf_path,statut FROM copie;
DROP TABLE copie;
ALTER TABLE copie_v4 RENAME TO copie;

CREATE UNIQUE INDEX copie_unique ON copie(sujet_id, eleve_id);

CREATE TRIGGER validate_copie_insert BEFORE INSERT ON copie
WHEN NEW.statut NOT IN ('present','absent')
 OR (NEW.eleve_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM eleve e JOIN sujet s ON s.classe=e.classe
    WHERE e.id=NEW.eleve_id AND s.id=NEW.sujet_id
 ))
 OR (NEW.version_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM version WHERE id=NEW.version_id AND sujet_id=NEW.sujet_id
 ))
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: copie'); END;

CREATE TRIGGER validate_copie_update BEFORE UPDATE ON copie
WHEN NEW.statut NOT IN ('present','absent')
 OR (NEW.eleve_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM eleve e JOIN sujet s ON s.classe=e.classe
    WHERE e.id=NEW.eleve_id AND s.id=NEW.sujet_id
 ))
 OR (NEW.version_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM version WHERE id=NEW.version_id AND sujet_id=NEW.sujet_id
 ))
BEGIN SELECT RAISE(ABORT, 'Relation ou valeur invalide: copie'); END;

CREATE TRIGGER freeze_copy_identity BEFORE UPDATE ON copie
WHEN EXISTS(SELECT 1 FROM correction WHERE copie_id=OLD.id) AND
 (
   NEW.sujet_id IS NOT OLD.sujet_id
   OR NEW.version_id IS NOT OLD.version_id
   OR NEW.statut IS NOT OLD.statut
   OR (OLD.eleve_id IS NOT NULL AND NEW.eleve_id IS NOT OLD.eleve_id)
 )
BEGIN SELECT RAISE(ABORT, 'Identité de copie déjà corrigée'); END;

CREATE TRIGGER freeze_copy_pdf BEFORE UPDATE OF pdf_path ON copie
WHEN NEW.pdf_path IS NOT OLD.pdf_path AND EXISTS(SELECT 1 FROM correction WHERE copie_id=OLD.id)
BEGIN SELECT RAISE(ABORT, 'PDF de copie déjà corrigée'); END;
'''


def connect(db_path=DEFAULT_DB):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


@contextmanager
def database(db_path=DEFAULT_DB):
    conn = connect(db_path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db(db_path=DEFAULT_DB):
    """Initialise ou migre SQLite de manière atomique.

    Les migrations préservent les notes et les identités existantes. Les anciennes
    grilles restent non validées et doivent être revues avant calcul.
    """
    conn = connect(db_path)
    try:
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError('Base plus récente que ce moteur')
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='item'").fetchone()
        if exists and version < 6:
            # Keep a recoverable snapshot before changing identity storage.
            backup_path = Path(db_path).with_name(Path(db_path).name+'.avant-identites-'+uuid.uuid4().hex[:8]+'.sqlite')
            backup = sqlite3.connect(backup_path)
            try:
                conn.backup(backup)
            finally:
                backup.close()
        migration = ''
        if exists and 'grille_id' not in {r['name'] for r in conn.execute('PRAGMA table_info(item)')}:
            migration = '''
ALTER TABLE copie ADD COLUMN statut TEXT NOT NULL DEFAULT 'present';
ALTER TABLE grille ADD COLUMN valide INTEGER NOT NULL DEFAULT 0;
CREATE TABLE item_new (
 id INTEGER PRIMARY KEY, question_id INTEGER NOT NULL REFERENCES question(id) ON DELETE CASCADE,
 grille_id INTEGER NOT NULL REFERENCES grille(id) ON DELETE CASCADE,
 code TEXT NOT NULL, description TEXT NOT NULL, bareme_max REAL NOT NULL,
 ordre INTEGER NOT NULL, regle_correction TEXT, UNIQUE(grille_id, code));
INSERT INTO item_new SELECT i.id,i.question_id,e.grille_id,i.code,i.description,i.bareme_max,i.ordre,i.regle_correction
 FROM item i JOIN question q ON q.id=i.question_id JOIN exercice e ON e.id=q.exercice_id;
DROP TABLE item;
ALTER TABLE item_new RENAME TO item;
'''
        conn.execute('PRAGMA foreign_keys = OFF')
        schema_path = Path(__file__).with_name('schema_legacy.sql') if version < 6 else SCHEMA
        base_schema = schema_path.read_text(encoding='utf-8') + '\n' + V3_SCHEMA
        script = 'BEGIN IMMEDIATE;\n' + migration + base_schema
        if version < 4:
            script += '\n' + V4_SCHEMA + '\n' + base_schema
        script += '\n' + Path(__file__).with_name('gui_schema.sql').read_text(encoding='utf-8')
        conn.executescript(script)
        if version < 6:
            # Existing IDs and all grading links survive; never guess which homonyms are one person.
            for trigger in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
                conn.execute('DROP TRIGGER "'+trigger[0].replace('"','""')+'"')
            conn.execute('CREATE TABLE eleve_classe (eleve_id INTEGER NOT NULL REFERENCES eleve(id), classe TEXT NOT NULL, numero INTEGER NOT NULL CHECK(numero>0), PRIMARY KEY(eleve_id,classe), UNIQUE(classe,numero))')
            conn.execute('INSERT INTO eleve_classe SELECT id,classe,numero FROM eleve')
            conn.execute('CREATE TABLE eleve_v6 (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT, prenom TEXT)')
            conn.execute('INSERT INTO eleve_v6 SELECT id,nom,prenom FROM eleve')
            conn.execute('DROP TABLE eleve')
            conn.execute('ALTER TABLE eleve_v6 RENAME TO eleve')
            # execute statements one by one: executescript would commit the pending migration.
            statement = ''
            for line in (SCHEMA.read_text(encoding='utf-8')+'\n'+V3_SCHEMA).splitlines(True):
                statement += line
                if sqlite3.complete_statement(statement):
                    conn.execute(statement)
                    statement = ''
            # Translate saved inventory drafts; a list position must never become another pupil's ID.
            for draft in conn.execute("SELECT b.*,d.classe FROM ui_brouillon b JOIN ui_dossier d ON d.id=b.dossier_id WHERE b.etape='copies'").fetchall():
                text = draft['texte'].strip()
                fenced = re.fullmatch(r'```(?:json)?\s*\n([\s\S]*?)\n```', text, re.IGNORECASE)
                try:
                    data = json.loads(fenced[1] if fenced else text)
                    mapping = {r['numero']:r['eleve_id'] for r in conn.execute('SELECT * FROM eleve_classe WHERE classe=?',(draft['classe'],))}
                    for copy in data.get('copies',[]):
                        if copy.get('numero') is not None:
                            copy['numero'] = mapping[copy['numero']]
                    data['absents'] = [mapping[n] for n in data.get('absents',[])]
                except (ValueError, TypeError, KeyError, AttributeError):
                    # Keep incomplete drafts verbatim; they still require teacher review before import.
                    continue
                conn.execute('UPDATE ui_brouillon SET texte=? WHERE dossier_id=? AND etape=?',
                             (json.dumps(data,ensure_ascii=False,indent=2),draft['dossier_id'],'copies'))
            conn.execute('''UPDATE ui_rendu SET valide=0 WHERE dossier_id IN
                (SELECT d.id FROM ui_dossier d JOIN eleve_classe e ON e.classe=d.classe WHERE e.numero<>e.eleve_id)''')
        errors = conn.execute('PRAGMA foreign_key_check').fetchall()
        if errors:
            raise ValueError(f'Intégrité de la base invalide : {len(errors)} liens')
        conn.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return Path(db_path)
