from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path('db/smartcorrection.sqlite')
SCHEMA = Path(__file__).with_name('schema.sql')
SCHEMA_VERSION = 2


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
    """Atomic additive v1 migration; existing scores and identities are preserved.

    Existing grids remain unvalidated and must be reviewed before calculation.
    Conflicting legacy duplicates abort migration rather than deleting data.
    """
    conn = connect(db_path)
    try:
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError('Base plus récente que ce moteur')
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='item'").fetchone()
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
        conn.executescript('BEGIN IMMEDIATE;\n' + migration + SCHEMA.read_text(encoding='utf-8'))
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
