"""Explicit deletion of a dossier's own data; reusable identities and policies survive."""
from pathlib import Path
import shutil
import tempfile
from .db import database


def delete_dossier(app, ident, confirmed=False):
    if confirmed is not True:
        raise ValueError('Confirmer la suppression de cette épreuve')
    moved = []
    quarantine = None
    try:
        with database(app.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            dossier = app._dossier(conn, ident)
            subjects = {r[0] for r in conn.execute('SELECT sujet_id FROM ui_revision WHERE dossier_id=?', (ident,))}
            if dossier['sujet_id']:
                subjects.add(dossier['sujet_id'])
            # Only directory roots owned by this dossier may be moved or removed.
            folders = [(app.data_dir/'documents'/ident, app.data_dir/'documents', ident)]
            folders += [(Path(r['chemin']), app.data_dir/'rendus', r['id']) for r in
                        conn.execute('SELECT id,chemin FROM ui_rendu WHERE dossier_id=?', (ident,))]
            for path, parent, name in folders:
                if path.is_symlink() or path.resolve().parent != parent.resolve() or path.name != name:
                    raise ValueError('Chemin de document inattendu : suppression annulée')
            quarantine = Path(tempfile.mkdtemp(prefix='.suppression-', dir=app.data_dir))
            for i, (path, _, _) in enumerate(folders):
                if path.exists():
                    target = quarantine/str(i)
                    path.rename(target)
                    moved.append((path, target))
            for table in ('ui_copie_exclue','ui_copie','ui_page_ignoree','ui_brouillon','ui_echange','ui_fichier','ui_rendu','ui_revision'):
                conn.execute(f'DELETE FROM {table} WHERE dossier_id=?', (ident,))
            conn.execute('DELETE FROM ui_dossier WHERE id=?', (ident,))
            for sid in subjects:
                shared = conn.execute('SELECT 1 FROM ui_dossier WHERE sujet_id=? UNION ALL SELECT 1 FROM ui_revision WHERE sujet_id=?', (sid,sid)).fetchone()
                if not shared:
                    conn.execute('DELETE FROM correction WHERE copie_id IN (SELECT id FROM copie WHERE sujet_id=?)', (sid,))
                    conn.execute('DELETE FROM copie WHERE sujet_id=?', (sid,))
                    conn.execute('DELETE FROM grille WHERE sujet_id=?', (sid,))
                    conn.execute('DELETE FROM sujet WHERE id=?', (sid,))
            for row in conn.execute('SELECT cle FROM ui_meta').fetchall():
                if ident in row['cle'].split(':'):
                    conn.execute('DELETE FROM ui_meta WHERE cle=?', (row['cle'],))
    except Exception:
        for original, target in reversed(moved):
            target.rename(original)
        if quarantine:
            quarantine.rmdir()
        raise
    warnings = []
    try:
        shutil.rmtree(quarantine)
    except OSError:
        warnings.append(f'Épreuve supprimée ; des fichiers verrouillés restent à nettoyer dans {quarantine}.')
    return {'supprime': True, 'avertissements': warnings}
