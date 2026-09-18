"""Application services shared by the local HTTP interface and integration tests."""
from __future__ import annotations
import base64
import difflib
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import threading
import uuid
from .db import database, init_db, ROOT
from .import_classe import _read_roster, import_classe_csv
from .identites import preview_roster
from .import_evaluation import import_evaluation
from .import_correction import import_correction, compatible_grid
from .calcul import calculate_selection
from .gui_groups import group_state, save_groups, copy_groups
from .render import export_results
from .validation import array, integer, number, object_fields, parse_json, string

INDIVIDUAL = {'note_individuelle': {'max': 20}, 'note_groupe': {'max': 0, 'mode': 'aucun'},
              'note_finale': {'max': 20, 'arrondi': .5}, 'absences': {'mode': 'exclure'}}


def public_json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def response_body(text, language):
    """Accept raw content or one copyable code block, never extract from prose."""
    if not isinstance(text, str):
        raise ValueError('Réponse : texte attendu')
    if '```' not in text:
        return text
    languages = r'(?:latex|tex)?' if language == 'latex' else r'(?:json)?'
    match = re.fullmatch(r'```' + languages + r'[ \t]*\r?\n([\s\S]*?)\r?\n```', text.strip(), re.IGNORECASE)
    if not match or re.search(r'^```', match[1], re.MULTILINE):
        raise ValueError('Coller un seul bloc de code complet, sans texte autour, ou utiliser son bouton Copier')
    return match[1]


def _put_instructions(conn, scope, classe, text, source=None):
    rid = conn.execute('INSERT INTO consigne_revision(portee,classe,texte,source_dossier) VALUES(?,?,?,?)',
                       (scope, classe, text, source)).lastrowid
    conn.execute('''INSERT INTO consigne_active VALUES(?,?,?) ON CONFLICT(portee,classe)
        DO UPDATE SET revision_id=excluded.revision_id''', (scope, classe, rid))
    return rid


def _policy(conn, scope, classe=''):
    row = conn.execute('''SELECT r.* FROM consigne_active a JOIN consigne_revision r ON r.id=a.revision_id
        WHERE a.portee=? AND a.classe=?''', (scope, classe.casefold())).fetchone()
    return dict(row) if row else {'id': None, 'texte': '', 'portee': scope, 'classe': classe}


class Application:
    def __init__(self, db_path, data_dir, legacy_dir=None):
        self.db_path = Path(db_path).resolve()
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        init_db(self.db_path)
        # One-time migration only. Future prompts read SQLite, never the old files.
        with database(self.db_path) as conn:
            if not conn.execute("SELECT 1 FROM ui_meta WHERE cle='consignes_md_importees'").fetchone():
                legacy = Path(legacy_dir) if legacy_dir is not None else (
                    Path.cwd()/'classes' if (Path.cwd()/'classes').is_dir() else ROOT/'classes')
                for path in sorted(legacy.glob('*.md')):
                    if path.stem.lower() == 'readme' or path.stem.startswith('_'):
                        continue
                    if _policy(conn, 'classe', path.stem)['id'] is None:
                        _put_instructions(conn, 'classe', path.stem.casefold(), path.read_text(encoding='utf-8'), 'migration Markdown')
                conn.execute("INSERT INTO ui_meta VALUES('consignes_md_importees','1')")

    def _dossier(self, conn, ident):
        row = conn.execute('SELECT * FROM ui_dossier WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Dossier introuvable')
        return row

    def _envelope(self, data, dossier, keys, required):
        object_fields(data, set(keys)|{'dossier','revision'}, set(required)|{'dossier','revision'})
        if data['dossier'] != dossier['id'] or type(data['revision']) is not int or data['revision'] != dossier['revision']:
            raise ValueError('Cette réponse vise un autre dossier ou une ancienne grille. Recopier la consigne actuelle.')

    def _record(self, conn, dossier, stage, data):
        conn.execute('INSERT INTO ui_echange(dossier_id,revision,etape,texte) VALUES(?,?,?,?)',
                     (dossier['id'], dossier['revision'], stage, public_json(data)))
        conn.execute('DELETE FROM ui_brouillon WHERE dossier_id=? AND etape=?', (dossier['id'], stage))

    def _copies(self, conn, dossier):
        rows = []
        for row in conn.execute('''SELECT u.*,c.sujet_id,c.eleve_id,c.version_id,c.pdf_path,c.statut,e.id numero,e.nom,e.prenom,
            v.version,co.id correction_id,x.reference IS NOT NULL exclue_final
            FROM ui_copie u JOIN copie c ON c.id=u.copie_id
            LEFT JOIN ui_copie_exclue x ON x.dossier_id=u.dossier_id AND x.reference=u.reference
            LEFT JOIN eleve e ON e.id=c.eleve_id JOIN version v ON v.id=c.version_id
            LEFT JOIN correction co ON co.copie_id=c.id WHERE u.dossier_id=? ORDER BY u.reference''', (dossier['id'],)):
            item = dict(row)
            item['pages'] = [r[0] for r in conn.execute('SELECT page FROM copie_page WHERE copie_id=? ORDER BY ordre', (row['copie_id'],))]
            rows.append(item)
        return rows

    def groups(self, ident, active, text):
        with database(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            return save_groups(conn,self._dossier(conn,ident),active,text,INDIVIDUAL)

    def home(self):
        with database(self.db_path) as conn:
            return {'classes': [dict(r) for r in conn.execute('SELECT classe,COUNT(*) effectif FROM eleve_classe GROUP BY classe ORDER BY classe')],
                    'dossiers': [dict(r) for r in conn.execute('SELECT * FROM ui_dossier ORDER BY cree_le DESC,id')],
                    'latex': bool(shutil.which('pdflatex'))}

    def state(self, ident):
        with database(self.db_path) as conn:
            dossier = self._dossier(conn, ident)
            grids, versions = [], []
            if dossier['sujet_id']:
                versions = [dict(r) for r in conn.execute('''SELECT v.id,v.version,co.str_latex corrige_latex FROM version v
                    LEFT JOIN corrige co ON co.version_id=v.id WHERE v.sujet_id=? ORDER BY v.id''', (dossier['sujet_id'],))]
                grids = [dict(r) for r in conn.execute('''SELECT i.code,i.description,i.bareme_max,i.regle_correction,
                    q.numero question,e.numero exercice,v.version FROM item i JOIN question q ON q.id=i.question_id
                    JOIN exercice e ON e.id=q.exercice_id JOIN grille g ON g.id=i.grille_id
                    LEFT JOIN version v ON v.id=g.version_id WHERE g.sujet_id=? ORDER BY g.id,e.ordre,q.ordre,i.ordre''', (dossier['sujet_id'],))]
            return {'dossier': dict(dossier), 'groupes': group_state(conn,dossier), 'copies': self._copies(conn, dossier), 'grille': grids, 'versions': versions,
                    'eleves': [dict(r) for r in conn.execute('SELECT id,id numero,nom,prenom FROM eleve_par_classe WHERE classe=? ORDER BY id', (dossier['classe'],))],
                    'fichiers': [dict(r) for r in conn.execute('SELECT id,role,nom,pages FROM ui_fichier WHERE dossier_id=?', (ident,))],
                    'brouillons': {r['etape']: r['texte'] for r in conn.execute('SELECT * FROM ui_brouillon WHERE dossier_id=?', (ident,))},
                    'rendus': [dict(id=r['id'], revision=r['revision'], final=r['final'], valide=r['valide'],
                                   cree_le=r['cree_le'], pdf=(Path(r['chemin'])/'corrections.pdf').is_file())
                               for r in conn.execute('SELECT * FROM ui_rendu WHERE dossier_id=? ORDER BY cree_le DESC,id DESC', (ident,))],
                    'consignes': {'generales': _policy(conn,'generale'), 'classe': _policy(conn,'classe',dossier['classe'])}}

    def roster(self, classe, text, commit=False, choices=None, fingerprint=None):
        string(classe, 'classe')
        if not isinstance(text, str):
            raise ValueError('CSV attendu')
        path = self.data_dir/f'{uuid.uuid4().hex}.csv'
        path.write_text(text, encoding='utf-8')
        try:
            if commit:
                return import_classe_csv(path, classe.strip(), self.db_path, choices=choices, fingerprint=fingerprint)
            with database(self.db_path) as conn:
                conn.execute('BEGIN')
                return preview_roster(conn, classe.strip(), _read_roster(path))
        finally:
            path.unlink(missing_ok=True)

    def create(self, classe, title):
        string(classe); string(title)
        with database(self.db_path) as conn:
            if not conn.execute('SELECT 1 FROM eleve_classe WHERE classe=?', (classe,)).fetchone():
                raise ValueError('Importer cette classe avant de créer le dossier')
            ident = uuid.uuid4().hex
            conn.execute('INSERT INTO ui_dossier(id,classe,titre,generale_id,classe_id) VALUES(?,?,?,?,?)',
                         (ident, classe, title, _policy(conn,'generale')['id'], _policy(conn,'classe',classe)['id']))
        return {'id': ident}

    def upload(self, ident, role, name, encoded):
        from pypdf import PdfReader
        if role not in {'paquet','sujet','corrige','cours','modele'}:
            raise ValueError('Type de document inconnu')
        string(name, 'nom du fichier')
        try:
            raw = base64.b64decode(encoded, validate=True)
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:
                raise ValueError('Le PDF est protégé par un mot de passe')
            pages = len(reader.pages)
        except Exception as exc:
            raise ValueError('PDF illisible, vide ou protégé') from exc
        if not pages or not raw.startswith(b'%PDF-'):
            raise ValueError('PDF vide ou invalide')
        fid = uuid.uuid4().hex
        folder = self.data_dir/'documents'/ident
        with database(self.db_path) as conn:
            self._dossier(conn, ident)
            if role == 'paquet' and conn.execute("SELECT 1 FROM ui_fichier WHERE dossier_id=? AND role='paquet'", (ident,)).fetchone():
                raise ValueError('Le paquet est déjà enregistré. Créer un autre dossier pour un nouveau PDF.')
            folder.mkdir(parents=True, exist_ok=True)
            path = folder/f'{fid}.pdf'
            path.write_bytes(raw)
            try:
                conn.execute('INSERT INTO ui_fichier VALUES(?,?,?,?,?,?,?)',
                             (fid, ident, role, name, str(path), pages, hashlib.sha256(raw).hexdigest()))
            except Exception:
                path.unlink(missing_ok=True)
                raise
        return {'id': fid, 'pages': pages}

    def draft(self, ident, stage, text):
        if stage not in {'grille','copies','correction','retour'} and not stage.startswith('corrige:'):
            raise ValueError('Étape inconnue')
        if not isinstance(text,str):
            raise ValueError('Texte attendu')
        with database(self.db_path) as conn:
            self._dossier(conn, ident)
            conn.execute('INSERT INTO ui_brouillon VALUES(?,?,?) ON CONFLICT(dossier_id,etape) DO UPDATE SET texte=excluded.texte', (ident, stage, text))
        return {'enregistre': True}

    def _packet(self, conn, ident):
        row = conn.execute("SELECT * FROM ui_fichier WHERE dossier_id=? AND role='paquet'", (ident,)).fetchone()
        if not row:
            raise ValueError('Ajouter le PDF du paquet avant cette étape')
        return row

    def exchange(self, ident, stage, text, commit=False):
        data = parse_json(response_body(text, 'json'))
        with database(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            dossier = self._dossier(conn, ident)
            if stage == 'grille':
                result = self._grid(conn, dossier, data)
            elif stage == 'copies':
                result = self._inventory(conn, dossier, data)
            elif stage == 'correction':
                result = self._corrections(conn, dossier, data)
            elif stage == 'retour':
                result = self._feedback(conn, dossier, data)
            else:
                raise ValueError('Étape inconnue')
            if commit:
                if stage != 'retour':
                    conn.execute('UPDATE ui_rendu SET valide=0 WHERE dossier_id=?', (ident,))
                self._record(conn, dossier, stage, data)
            else:
                conn.rollback()
            return result

    def _grid(self, conn, dossier, data):
        self._envelope(data, dossier, {'versions','grilles'}, {'versions','grilles'})
        versions = []
        for v in array(data['versions'], 'versions', True):
            object_fields(v, {'version','sujet_latex'}, {'version'})
            versions.append({'version': string(v['version']), 'str_latex': v.get('sujet_latex') or r'\textit{Sujet joint en PDF.}'})
        grids = array(data['grilles'], 'grilles', True)
        for grid in grids:
            if not isinstance(grid,dict) or 'validee' in grid:
                raise ValueError('La validation de la grille appartient à l’enseignant dans l’application')
        evaluation = {'cle': f"interface-{dossier['id']}-{dossier['revision']+1}",
                      'sujet': {'classe': dossier['classe'], 'titre': dossier['titre'], 'config_notes': INDIVIDUAL},
                      'versions': versions, 'grilles': [dict(g,validee=True) for g in grids]}
        sid = import_evaluation(evaluation, conn)
        copy_groups(conn,dossier['sujet_id'],sid)
        # Preserve the original subjects/corrections, create a new revision using stable public references.
        copies = self._copies(conn,dossier)
        version_ids = {r['version']: r['id'] for r in conn.execute('SELECT * FROM version WHERE sujet_id=?', (sid,))}
        for copy in copies:
            if copy['version'] not in version_ids:
                raise ValueError(f"La copie {copy['reference']} utilise encore la version {copy['version']}")
            cid = conn.execute('INSERT INTO copie(eleve_id,sujet_id,version_id,pdf_path,statut) VALUES(?,?,?,?,?)',
                               (copy['eleve_id'],sid,version_ids[copy['version']],copy['pdf_path'],copy['statut'])).lastrowid
            for order,page in enumerate(copy['pages'],1):
                conn.execute('INSERT INTO copie_page VALUES(?,?,?)',(cid,page,order))
            conn.execute('UPDATE ui_copie SET copie_id=?,a_revoir=NULL WHERE dossier_id=? AND reference=?',(cid,dossier['id'],copy['reference']))
        conn.execute('UPDATE ui_dossier SET sujet_id=?,revision=revision+1,echantillon_valide=0,termine=0 WHERE id=?',(sid,dossier['id']))
        conn.execute('INSERT INTO ui_revision VALUES(?,?,?)',(dossier['id'],dossier['revision']+1,sid))
        return {'grilles': [dict(r) for r in conn.execute('SELECT id,nom,total_points FROM grille WHERE sujet_id=?',(sid,))],
                'copies_a_reprendre': len([c for c in copies if c['correction_id']]), 'revision': dossier['revision']+1}

    def corrige(self, ident, version, text, commit=False):
        text = response_body(text, 'latex')
        string(text, 'corrigé LaTeX')
        if any(word in text for word in (r'\documentclass',r'\begin{document}',r'\end{document}')):
            raise ValueError('Coller uniquement le corps du corrigé, sans préambule ni début/fin de document')
        with database(self.db_path) as conn:
            dossier = self._dossier(conn, ident)
            v = conn.execute('SELECT id FROM version WHERE sujet_id=? AND version=?',(dossier['sujet_id'],version)).fetchone()
            if not v:
                raise ValueError('Version inconnue')
            if commit:
                previous = conn.execute('SELECT str_latex FROM corrige WHERE version_id=?',(v['id'],)).fetchone()
                conn.execute('INSERT INTO corrige(version_id,str_latex) VALUES(?,?) ON CONFLICT(version_id) DO UPDATE SET str_latex=excluded.str_latex',(v['id'],text))
                if previous and previous[0] != text:
                    conn.execute('''UPDATE ui_copie SET a_revoir='Corrigé de référence modifié : vérifier cette correction'
                        WHERE dossier_id=? AND copie_id IN (SELECT co.copie_id FROM correction co JOIN copie c ON c.id=co.copie_id WHERE c.version_id=?)''',(ident,v['id']))
                conn.execute('UPDATE ui_dossier SET echantillon_valide=0,termine=0 WHERE id=?',(ident,))
                conn.execute('UPDATE ui_rendu SET valide=0 WHERE dossier_id=?',(ident,))
                self._record(conn,dossier,'corrige:'+version, {'version':version,'latex':text})
        return {'version': version, 'caracteres': len(text)}

    def _inventory(self, conn, dossier, data):
        self._envelope(data, dossier, {'copies','pages_ignorees','absents'}, {'copies','pages_ignorees'})
        if not dossier['sujet_id']:
            raise ValueError('Valider la grille avant les copies')
        packet = self._packet(conn,dossier['id'])
        versions = {r['version']:r['id'] for r in conn.execute('SELECT * FROM version WHERE sujet_id=?',(dossier['sujet_id'],))}
        pupils = {r['numero']:r['id'] for r in conn.execute('SELECT id,id numero,nom,prenom FROM eleve_par_classe WHERE classe=?',(dossier['classe'],))}
        existing = {c['reference']:c for c in self._copies(conn,dossier)}
        entries, covered, references, numbers = [], set(), set(), set()
        for item in array(data['copies'],'copies',True):
            object_fields(item, {'reference','numero','version','pages'}, {'reference','numero','version','pages'})
            reference = string(item['reference'])
            if not re.fullmatch(r'C\d{3,6}',reference) or reference in references:
                raise ValueError('Référence de copie répétée ou invalide : utiliser C001, C002…')
            references.add(reference)
            num = item['numero']
            if num is not None:
                integer(num,'numero')
                if num not in pupils or num in numbers:
                    raise ValueError(f'Numéro d’élève inconnu ou répété : {num}')
                numbers.add(num)
            version = string(item['version'])
            if version not in versions:
                raise ValueError(f'Version inconnue : {version}')
            pages = array(item['pages'],'pages',True)
            for page in pages:
                integer(page,'page')
                if page > packet['pages'] or page in covered:
                    raise ValueError(f'Page {page} inexistante ou attribuée deux fois')
                covered.add(page)
            if pages != sorted(pages):
                raise ValueError('Indiquer les pages dans l’ordre du paquet')
            entries.append(dict(item,eleve_id=pupils.get(num),version_id=versions[version],statut='present'))
        ignored = []
        for item in array(data['pages_ignorees'],'pages_ignorees'):
            object_fields(item, {'page','motif'}, {'page','motif'})
            page = integer(item['page'],'page ignorée')
            if page > packet['pages'] or page in covered:
                raise ValueError('Page ignorée déjà affectée ou inexistante')
            covered.add(page)
            ignored.append((page,string(item['motif'])))
        missing = sorted(set(range(1,packet['pages']+1))-covered)
        if missing:
            raise ValueError(f'Pages non affectées : {missing}. Les affecter à une copie ou préciser pourquoi elles sont ignorées.')
        for num in array(data.get('absents',[]),'absents'):
            integer(num,'absent')
            if num not in pupils or num in numbers:
                raise ValueError('Élève absent inconnu ou déjà présent')
            numbers.add(num)
            ref=f'ABS{num:03d}';references.add(ref)
            entries.append({'reference':ref,'numero':num,'eleve_id':pupils[num], 'version_id':next(iter(versions.values())), 'pages':[], 'statut':'absent'})
        # Never remove an already graded copy silently. The original subject remains in revision history.
        for ref, old in existing.items():
            if ref not in references and old['correction_id']:
                raise ValueError(f'{ref} est déjà corrigée ; créer une nouvelle révision de grille avant de retirer cette copie')
        # Release only the ungraded page mappings, so editing boundaries is order independent.
        for old in existing.values():
            if not old['correction_id']:
                conn.execute('DELETE FROM copie_page WHERE copie_id=?',(old['copie_id'],))
                conn.execute('UPDATE copie SET eleve_id=NULL WHERE id=?',(old['copie_id'],))
        for ref,old in existing.items():
            if ref not in references:
                conn.execute('DELETE FROM ui_copie WHERE dossier_id=? AND reference=?',(dossier['id'],ref))
                conn.execute('DELETE FROM copie WHERE id=?',(old['copie_id'],))
        for item in entries:
            old=existing.get(item['reference'])
            if old and old['correction_id']:
                if old['version_id']!=item['version_id'] or old['pages']!=item['pages'] or old['statut']!=item['statut']:
                    raise ValueError(f"Pages ou version de {item['reference']} déjà corrigées : créer une nouvelle révision de grille")
                if old['eleve_id'] is not None and old['eleve_id']!=item['eleve_id']:
                    raise ValueError(f"Identité de {item['reference']} déjà corrigée : association existante à conserver")
                conn.execute('UPDATE copie SET eleve_id=? WHERE id=?',(item['eleve_id'],old['copie_id']))
                continue
            pdf=packet['chemin'] if item['statut']=='present' else ''
            if old:
                cid=old['copie_id']
                conn.execute('UPDATE copie SET eleve_id=?,version_id=?,pdf_path=?,statut=? WHERE id=?',
                             (item['eleve_id'],item['version_id'],pdf,item['statut'],cid))
            else:
                cid=conn.execute('INSERT INTO copie(eleve_id,sujet_id,version_id,pdf_path,statut) VALUES(?,?,?,?,?)',
                                 (item['eleve_id'],dossier['sujet_id'],item['version_id'],pdf,item['statut'])).lastrowid
                conn.execute('INSERT INTO ui_copie(dossier_id,reference,copie_id) VALUES(?,?,?)',(dossier['id'],item['reference'],cid))
            for order,page in enumerate(item['pages'],1):
                conn.execute('INSERT INTO copie_page VALUES(?,?,?)',(cid,page,order))
        conn.execute('DELETE FROM ui_page_ignoree WHERE dossier_id=?',(dossier['id'],))
        for page,motif in ignored:
            conn.execute('INSERT INTO ui_page_ignoree VALUES(?,?,?)',(dossier['id'],page,motif))
        if not existing:
            for item in [x for x in entries if x['statut']=='present'][:5]:
                conn.execute('UPDATE ui_copie SET echantillon=1 WHERE dossier_id=? AND reference=?',(dossier['id'],item['reference']))
        conn.execute('UPDATE ui_dossier SET echantillon_valide=0,termine=0 WHERE id=?',(dossier['id'],))
        return {'copies':self._copies(conn,dossier), 'pages_ignorees':len(ignored),
                'sans_copie_reperee':sorted(set(pupils)-numbers)}

    def sample(self, ident, references, approve=False):
        with database(self.db_path) as conn:
            dossier=self._dossier(conn,ident)
            copies={c['reference']:c for c in self._copies(conn,dossier)}
            array(references,'échantillon',True)
            if len(references)>5 or len(set(references))!=len(references):
                raise ValueError('Sélectionner entre une et cinq copies distinctes')
            for ref in references:
                if ref not in copies or copies[ref]['statut']!='present':
                    raise ValueError('Copie présente introuvable dans l’échantillon')
                if approve and (not copies[ref]['correction_id'] or copies[ref]['a_revoir']):
                    raise ValueError(f'{ref} doit être corrigée et vérifiée avant validation')
            old={c['reference'] for c in copies.values() if c['echantillon']}
            if approve and set(references)!=old:
                raise ValueError('Enregistrer cette sélection avant de valider l’échantillon')
            conn.execute('UPDATE ui_copie SET echantillon=0 WHERE dossier_id=?',(ident,))
            for ref in references:
                conn.execute('UPDATE ui_copie SET echantillon=1 WHERE dossier_id=? AND reference=?',(ident,ref))
            conn.execute('UPDATE ui_dossier SET echantillon_valide=?,termine=CASE WHEN ? THEN termine ELSE 0 END WHERE id=?',(int(approve),int(approve),ident))
            if not approve:
                conn.execute('UPDATE ui_rendu SET valide=0 WHERE dossier_id=?',(ident,))
        return {'echantillon_valide':approve}

    def _corrections(self, conn, dossier, data):
        self._envelope(data,dossier,{'corrections','a_revoir'},{'corrections'})
        copies={c['reference']:c for c in self._copies(conn,dossier)}
        seen=set();summary=[]
        for correction in array(data['corrections'],'corrections'):
            object_fields(correction,{'reference','items','annotations','conseils','commentaire_global','a_verifier'},{'reference','items'})
            ref=string(correction['reference'])
            if ref in seen or ref not in copies:
                raise ValueError(f'Copie répétée ou inconnue : {ref}')
            seen.add(ref);copy=copies[ref]
            if not dossier['echantillon_valide'] and not copy['echantillon']:
                raise ValueError('Valider l’échantillon avant de corriger le reste')
            if not conn.execute('SELECT 1 FROM corrige WHERE version_id=?',(copy['version_id'],)).fetchone():
                raise ValueError(f'Enregistrer le corrigé de la version {copy["version"]} avant cette correction')
            grid_id=compatible_grid(conn,copy)
            maxima={r['code']:r['bareme_max'] for r in conn.execute('SELECT * FROM item WHERE grille_id=?',(grid_id,))}
            for item in array(correction['items'],'items',True):
                if not isinstance(item,dict):
                    raise ValueError('Chaque item doit être un objet')
                code=string(item.get('item_code'),'item_code')
                if code not in maxima:
                    raise ValueError(f'Item inconnu : {code}')
                points=number(item.get('points_obtenus'),'points obtenus')
                if points<maxima[code] and not (item.get('commentaire') or item.get('annotation')):
                    raise ValueError(f'{ref} / {code} : expliquer les points non attribués')
            for annotation in array(correction.get('annotations',[]),'annotations'):
                if not isinstance(annotation,dict) or annotation.get('page') not in copy['pages']:
                    raise ValueError(f'{ref} : annotation sur une page extérieure à la copie')
            checks=[string(x,'élément à vérifier').strip() for x in array(correction.get('a_verifier',[]),'a_verifier')]
            checks=[x for x in checks if x]
            payload={k:v for k,v in correction.items() if k not in {'reference','a_verifier'}}
            payload.update(copie_id=copy['copie_id'],grille_id=grid_id)
            cid=import_correction(payload,conn,replace=True)
            conn.execute('DELETE FROM ui_verification WHERE copie_id=?',(copy['copie_id'],))
            for order,text in enumerate(checks,1):
                conn.execute('INSERT INTO ui_verification(copie_id,ordre,texte) VALUES(?,?,?)',(copy['copie_id'],order,text))
            conn.execute('UPDATE ui_copie SET a_revoir=NULL WHERE dossier_id=? AND reference=?',(dossier['id'],ref))
            score=conn.execute('SELECT note_brute FROM correction WHERE id=?',(cid,)).fetchone()[0]
            summary.append({'reference':ref,'note_brute':score,'bareme':sum(maxima.values()),'remplacement':bool(copy['correction_id'])})
        pending=[]
        for entry in array(data.get('a_revoir',[]),'a_revoir'):
            object_fields(entry,{'reference','motif'},{'reference','motif'})
            ref=string(entry['reference'])
            if ref not in copies or ref in seen or copies[ref]['statut']!='present':
                raise ValueError('Copie à revoir inconnue ou répétée')
            if not dossier['echantillon_valide'] and not copies[ref]['echantillon']:
                raise ValueError('Cette copie ne fait pas partie de l’échantillon')
            seen.add(ref)
            conn.execute('UPDATE ui_copie SET a_revoir=? WHERE dossier_id=? AND reference=?',(string(entry['motif']),dossier['id'],ref))
            pending.append(entry)
        if not seen:
            raise ValueError('La réponse ne contient aucune copie')
        conn.execute('UPDATE ui_dossier SET termine=0 WHERE id=?',(dossier['id'],))
        if any(copies[ref]['echantillon'] for ref in seen):
            conn.execute('UPDATE ui_dossier SET echantillon_valide=0 WHERE id=?',(dossier['id'],))
        return {'corrections':summary,'a_revoir':pending}

    def review(self, ident, reference):
        """Teacher explicitly confirms a previously graded copy after a reference correction change."""
        with database(self.db_path) as conn:
            dossier=self._dossier(conn,ident)
            copy=next((c for c in self._copies(conn,dossier) if c['reference']==reference),None)
            if not copy or not copy['correction_id']:
                raise ValueError('Une correction complète est nécessaire avant confirmation')
            calculate_selection(conn,dossier['sujet_id'],[copy['copie_id']],allow_groups=True)
            conn.execute('UPDATE ui_copie SET a_revoir=NULL WHERE dossier_id=? AND reference=?',(ident,reference))
            self._record(conn,dossier,'revue',{'reference':reference})
        return {'verifiee':reference}

    def include_in_final(self, ident, reference, include):
        """Persist a reversible output choice without changing scores or attendance."""
        if type(include) is not bool:
            raise ValueError('Inclure doit être un booléen')
        string(reference, 'référence de copie')
        with database(self.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            dossier = self._dossier(conn, ident)
            copy = next((c for c in self._copies(conn, dossier) if c['reference'] == reference), None)
            if not copy:
                raise ValueError('Copie introuvable dans ce dossier')
            if bool(copy['exclue_final']) == include:
                if include:
                    conn.execute('DELETE FROM ui_copie_exclue WHERE dossier_id=? AND reference=?', (ident, reference))
                else:
                    conn.execute('INSERT INTO ui_copie_exclue VALUES(?,?)', (ident, reference))
                conn.execute('UPDATE ui_rendu SET valide=0 WHERE dossier_id=? AND final=1', (ident,))
                conn.execute('UPDATE ui_dossier SET termine=0 WHERE id=?', (ident,))
                self._record(conn, dossier, 'selection_finale', {'reference': reference, 'inclure': include})
        return {'reference': reference, 'inclure': include}

    def generate(self, ident, final=False, pdf=True):
        with database(self.db_path) as conn:
            dossier=self._dossier(conn,ident)
            copies=self._copies(conn,dossier)
            if final and not dossier['echantillon_valide']:
                raise ValueError('Valider l’échantillon avant le document final')
            selected=[c for c in copies if not c['exclue_final']] if final else [c for c in copies if c['echantillon']]
            if not selected:
                raise ValueError('Inclure au moins une copie dans le document final' if final else 'Sélectionner des copies à afficher')
            for copy in selected:
                if copy['a_revoir']:
                    raise ValueError(f"{copy['reference']} reste à revoir : {copy['a_revoir']}")
            result=calculate_selection(conn,dossier['sujet_id'],[c['copie_id'] for c in selected],allow_groups=True)
            if final:
                result['copies_exclues'] = [c['reference'] for c in copies if c['exclue_final']]
            labels={c['copie_id']:c['reference'] for c in selected}
            for row in result['notes']:
                if row['numero'] is None:
                    row['label']=f"{labels[row['copie_id']]} - élève non identifié"
            rid=uuid.uuid4().hex
            folder=self.data_dir/'rendus'/rid
            export_results(conn,result,folder,pdf=pdf,combined=pdf)
            conn.execute('INSERT INTO ui_rendu(id,dossier_id,revision,final,chemin) VALUES(?,?,?,?,?)',(rid,ident,dossier['revision'],int(final),str(folder)))
            if final:
                conn.execute('UPDATE ui_dossier SET termine=1 WHERE id=?',(ident,))
        return {'id':rid,'pdf':pdf,'fichiers':sorted(p.name for p in folder.iterdir())}

    def _feedback(self, conn, dossier, data):
        self._envelope(data,dossier,{'base_generale','base_classe','generales','classe'}, {'base_generale','base_classe','generales','classe'})
        if not dossier['termine']:
            raise ValueError('Produire le document final avant le retour d’expérience')
        result={}
        for scope,key,base_key,classe in [('generale','generales','base_generale',''),('classe','classe','base_classe',dossier['classe'].casefold())]:
            current=_policy(conn,scope,classe)
            if data[base_key] is not None and type(data[base_key]) is not int:
                raise ValueError(f'{base_key} doit être un entier ou null')
            if data[base_key] != current['id']:
                raise ValueError('Les consignes ont été mises à jour depuis cette proposition. Recopier la consigne de retour d’expérience.')
            text=data[key]
            if not isinstance(text,str):
                raise ValueError(f'{key} doit être un texte complet')
            diff='\n'.join(difflib.unified_diff(current['texte'].splitlines(),text.splitlines(),fromfile='Consignes actuelles',tofile='Proposition',lineterm=''))
            rid=_put_instructions(conn,scope,classe,text,dossier['id'])
            result[key]={'avant':current['texte'],'apres':text,'diff':diff,'revision':rid}
        return result

    def instruction_history(self, classe):
        with database(self.db_path) as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM consigne_revision WHERE portee='generale' OR classe=? ORDER BY id DESC",(classe.casefold(),))]

    def file(self, kind, ident, name=None):
        with database(self.db_path) as conn:
            if kind=='source':
                row=conn.execute('SELECT chemin FROM ui_fichier WHERE id=?',(ident,)).fetchone()
                if not row:
                    raise ValueError('Document introuvable')
                path=Path(row['chemin'])
            elif kind=='rendu':
                row=conn.execute('SELECT chemin FROM ui_rendu WHERE id=?',(ident,)).fetchone()
                if not row or not name or Path(name).name!=name or '\\' in name:
                    raise ValueError('Rendu introuvable')
                path=Path(row['chemin'])/name
                if path.suffix not in {'.pdf','.tex','.json','.csv','.md'}:
                    raise ValueError('Format non disponible')
            else:
                raise ValueError('Document inconnu')
        if not path.resolve().is_relative_to(self.data_dir) or not path.is_file():
            raise ValueError('Fichier indisponible')
        return path
