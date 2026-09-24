"""Versioned pedagogical instructions, independent from the fixed JSON contract."""
from .db import database


def type_name(value):
    if not isinstance(value, str) or len(value.strip()) > 80:
        raise ValueError('Type d’épreuve : texte de 80 caractères maximum attendu')
    return ' '.join(value.split()).casefold()


def type_policy(conn, classe, kind):
    row = conn.execute('''SELECT * FROM consigne_type_revision WHERE classe=? AND type_epreuve=?
                          ORDER BY id DESC LIMIT 1''', (classe.casefold(), kind)).fetchone()
    return dict(row) if row else {'id': None, 'texte': '', 'classe': classe, 'type_epreuve': kind}


def put_type(conn, classe, kind, text, source=None):
    return conn.execute('''INSERT INTO consigne_type_revision(classe,type_epreuve,texte,source_dossier)
                           VALUES(?,?,?,?)''', (classe.casefold(), kind, text, source)).lastrowid


def policies(app, classe='', kind=''):
    from .gui_service import _policy
    kind = type_name(kind)
    with database(app.db_path) as conn:
        return {'generales': _policy(conn, 'generale'), 'classe': _policy(conn, 'classe', classe),
                'type': type_policy(conn, classe, kind),
                'historique_type': [dict(r) for r in conn.execute('''SELECT * FROM consigne_type_revision
                    WHERE classe=? AND type_epreuve=? ORDER BY id DESC''', (classe.casefold(), kind))]}


def replace_policy(app, scope, classe, kind, text, base):
    from .gui_service import _policy, _put_instructions
    if scope not in {'generales', 'classe', 'type'} or not isinstance(text, str):
        raise ValueError('Consigne : portée et texte attendus')
    if base is not None and type(base) is not int:
        raise ValueError('Version de base invalide')
    kind = type_name(kind)
    with database(app.db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        if scope != 'generales' and not conn.execute('SELECT 1 FROM eleve_classe WHERE classe=?', (classe,)).fetchone():
            raise ValueError('Choisir une classe existante')
        if scope == 'type' and not kind:
            raise ValueError('Choisir un type d’épreuve')
        key = 'generale' if scope == 'generales' else 'classe'
        current = type_policy(conn, classe, kind) if scope == 'type' else _policy(conn, key, '' if scope == 'generales' else classe)
        if current['id'] != base:
            raise ValueError('Les consignes ont changé. Rechargez-les avant de remplacer le texte.')
        rid = put_type(conn, classe, kind, text) if scope == 'type' else _put_instructions(conn, key, '' if scope == 'generales' else classe.casefold(), text)
        return {'revision': rid}


def set_type(app, ident, kind):
    kind = type_name(kind)
    with database(app.db_path) as conn:
        app._dossier(conn, ident)
        conn.execute('''INSERT INTO ui_type_epreuve VALUES(?,?) ON CONFLICT(dossier_id)
                        DO UPDATE SET type_epreuve=excluded.type_epreuve''', (ident, kind))
    return {'type_epreuve': kind}
