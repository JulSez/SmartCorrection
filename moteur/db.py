from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "db" / "smartcorrection.sqlite"
SCHEMA = ROOT / "db" / "schema.sql"


def connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path = DEFAULT_DB) -> Path:
    schema = SCHEMA.read_text(encoding="utf-8")
    with connect(db_path) as conn:
        conn.executescript(schema)
    return Path(db_path)
