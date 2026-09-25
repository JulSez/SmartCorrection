"""Fast four-step workflow: barème, iterative calibration, full correction, results."""
from __future__ import annotations

import json

from .db import database
from .gui_service import Application as BaseApplication, public_json, response_body
from .validation import array, number, object_fields, parse_json, string
from .correction_contract import normalize_corrections
from . import gui_prompts_v2 as prompts
from . import pr20_patch as pr20
from . import pr25_patch as pr25
from . import workflow_v2 as workflow

WorkflowApplication = workflow.WorkflowApplication
_BASE_STATE = WorkflowApplication.state
_BASE_DRAFT = WorkflowApplication.draft
_BASE_EXCHANGE = WorkflowApplication.exchange
_BASE_PROMPT = prompts.make_prompt

_RETURNS_KEY = "workflow-calibrage-retours:{}"
_MEAN_KEY = "workflow-calibrage-moyenne:{}"


def _meta(conn, key):
    row = conn.execute("SELECT valeur FROM ui_meta WHERE cle=?", (key,)).fetchone()
    return row[0] if row else ""


def _set_meta(conn, key, value):
    conn.execute("""INSERT INTO ui_meta(cle,valeur) VALUES(?,?)
        ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur""", (key, value))


def _state(self, ident):
    result = _BASE_STATE(self, ident)
    with database(self.db_path) as conn:
        result["calibrage"] = {
            "retours": _meta(conn, _RETURNS_KEY.format(ident)),
            "moyenne_estimee": _meta(conn, _MEAN_KEY.format(ident)) or None,
        }
    return result


def _draft(self, ident, stage, text):
    if stage in {'bareme', 'calibrage'}:
        if not isinstance(text, str):
            raise ValueError('Texte attendu')
        with database(self.db_path) as conn:
            self._dossier(conn, ident)
            conn.execute('INSERT INTO ui_brouillon VALUES(?,?,?) ON CONFLICT(dossier_id,etape) DO UPDATE SET texte=excluded.texte', (ident,stage,text))
        return {'enregistre': True}
    if stage != "calibrage-retours":
        return _BASE_DRAFT(self, ident, stage, text)
    if not isinstance(text, str):
        raise ValueError("Texte attendu")
    clean = text.strip()
    if not clean:
        return {"enregistre": False}
    with database(self.db_path) as conn:
        self._dossier(conn, ident)
        old = _meta(conn, _RETURNS_KEY.format(ident)).strip()
        combined = (old + "\n\n" if old else "") + clean
        if old == clean or old.endswith('\n\n'+clean):
            return {'enregistre': False}
        _set_meta(conn, _RETURNS_KEY.format(ident), combined)
        conn.execute("""UPDATE ui_copie SET a_revoir=COALESCE(a_revoir || '\n', '') ||
            'Consignes de calibrage modifiées : reprendre cette correction'
            WHERE dossier_id=? AND copie_id IN (SELECT copie_id FROM correction)""", (ident,))
        conn.execute('UPDATE ui_dossier SET echantillon_valide=0,termine=0 WHERE id=?', (ident,))
        conn.execute('UPDATE ui_rendu SET valide=0 WHERE dossier_id=?', (ident,))
    return {"enregistre": True}


def _bareme(self, conn, dossier, data):
    """Import the rubric and reference correction in one transaction."""
    result = BaseApplication._grid(self, conn, dossier, {k:v for k,v in data.items() if k != 'corriges'})
    if 'corriges' in data:
        _save_corriges(conn, self._dossier(conn, dossier['id']), data['corriges'])
    return dict(result, bareme_valide=True)


def _save_corriges(conn, dossier, entries):
    versions = {r["version"]: r["id"] for r in conn.execute(
        "SELECT id,version FROM version WHERE sujet_id=?", (dossier["sujet_id"],))}
    seen = set()
    for item in array(entries, "corriges", True):
        object_fields(item, {"version", "corrige_latex", "sujet_latex"}, {"version", "corrige_latex"})
        version = string(item["version"], "version").strip()
        if version not in versions or version in seen:
            raise ValueError(f"Version de corrigé invalide ou répétée : {version}")
        seen.add(version)
        latex = string(item["corrige_latex"], f"corrigé {version}")
        if any(word in latex for word in (r"\documentclass", r"\begin{document}", r"\end{document}")):
            raise ValueError(f"Corrigé {version} : fournir uniquement le corps LaTeX")
        old = conn.execute('SELECT str_latex FROM corrige WHERE version_id=?', (versions[version],)).fetchone()
        if old and old[0] != latex:
            conn.execute("""UPDATE ui_copie SET a_revoir=COALESCE(a_revoir || '\n', '') ||
                'Corrigé de référence modifié : vérifier cette correction'
                WHERE dossier_id=? AND copie_id IN
                (SELECT c.id FROM copie c JOIN correction co ON co.copie_id=c.id WHERE c.version_id=?)""",
                (dossier['id'], versions[version]))
        conn.execute("""INSERT INTO corrige(version_id,str_latex) VALUES(?,?)
            ON CONFLICT(version_id) DO UPDATE SET str_latex=excluded.str_latex""",
            (versions[version], latex))
    if seen != set(versions):
        missing = ", ".join(sorted(set(versions) - seen))
        raise ValueError(f"Corrigé manquant pour : {missing}")


def _calibration(self, conn, dossier, data):
    allowed = {"dossier", "revision", "pretraitement", "corriges", "corrections", "a_revoir", "moyenne_estimee"}
    self._envelope(data, dossier, allowed, {"corrections"})

    prep = pr20._read_preprocessing(conn, dossier["id"])
    if prep and 'pretraitement' in data:
        raw = data['pretraitement']
        if not isinstance(raw, dict):
            raise ValueError('Prétraitement : objet attendu')
        supplied = pr25._validate_preprocessing(dict(raw, dossier=dossier['id'], revision=dossier['revision']), dossier, pr20._anonymity(conn,dossier['id']))
        def inventory(value):
            fields = ('reference','version','pages','identite_lue','nom','prenom')
            return (sorted([{k:c.get(k) for k in fields} for c in value['copies']], key=lambda c:c['reference']),
                    sorted(value['pages_ignorees'],key=lambda p:p['page']))
        if inventory(supplied) != inventory(prep):
            raise ValueError('Inventaire différent : modifier les affectations séparément de la correction')

    if not prep:
        raw = data.get("pretraitement")
        if not isinstance(raw, dict):
            raise ValueError("Le premier JSON de calibrage doit contenir pretraitement.")
        packed = dict(raw, dossier=dossier["id"], revision=dossier["revision"])
        # numero is a local roster field, not something the AI should have to invent.
        # Accept its omission in the calibration JSON and normalize it to null.
        copies = packed.get("copies")
        if isinstance(copies, list):
            packed["copies"] = [dict(item, numero=item.get("numero")) if isinstance(item, dict) else item for item in copies]
        prep = pr25._validate_preprocessing(packed, dossier, pr20._anonymity(conn, dossier["id"]))
        _set_meta(conn, pr20._meta_key(dossier["id"]), json.dumps(prep, ensure_ascii=False))
        pr20._materialize_preprocessing(conn, dossier, prep)

    dossier = self._dossier(conn, dossier["id"])
    existing_corriges = conn.execute("""SELECT COUNT(*) n FROM corrige co
        JOIN version v ON v.id=co.version_id WHERE v.sujet_id=?""", (dossier["sujet_id"],)).fetchone()["n"]
    version_count = conn.execute("SELECT COUNT(*) n FROM version WHERE sujet_id=?", (dossier["sujet_id"],)).fetchone()["n"]
    if existing_corriges < version_count:
        if "corriges" not in data:
            raise ValueError("Le premier JSON de calibrage doit contenir tous les corrigés de référence.")
        _save_corriges(conn, dossier, data["corriges"])
    elif "corriges" in data:
        _save_corriges(conn, dossier, data["corriges"])

    corrections = normalize_corrections(data['corrections'])
    pending = array(data.get('a_revoir', []), 'a_revoir')
    refs = []
    for entries, label in ((corrections, 'corrections'), (pending, 'a_revoir')):
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError(f'{label}[{i}]: objet attendu')
            refs.append(string(entry.get('reference'), f'{label}[{i}].reference'))
    if not 1 <= len(refs) <= 5 or len(set(refs)) != len(refs):
        raise ValueError("Le lot de calibrage doit contenir entre 1 et 5 copies distinctes.")

    conn.execute("UPDATE ui_copie SET echantillon=0 WHERE dossier_id=?", (dossier["id"],))
    for ref in refs:
        row = conn.execute("SELECT 1 FROM ui_copie WHERE dossier_id=? AND reference=?", (dossier["id"], ref)).fetchone()
        if not row:
            raise ValueError(f"Copie inconnue dans le calibrage : {ref}")
        conn.execute("UPDATE ui_copie SET echantillon=1 WHERE dossier_id=? AND reference=?", (dossier["id"], ref))

    payload = {
        "dossier": dossier["id"], "revision": dossier["revision"],
        "corrections": corrections, "a_revoir": data.get("a_revoir", []),
    }
    summary = BaseApplication._corrections(self, conn, dossier, payload)
    mean = _meta(conn, _MEAN_KEY.format(dossier['id'])) or None
    if 'moyenne_estimee' in data:
        mean = number(data['moyenne_estimee'], 'moyenne estimée')
        if not 0 <= mean <= 20:
            raise ValueError('La moyenne estimée doit être comprise entre 0 et 20.')
        _set_meta(conn, _MEAN_KEY.format(dossier['id']), str(mean))
    return {"lot": refs, "moyenne_estimee": mean, "corrections": summary}


def _exchange(self, ident, stage, text, commit=False):
    if stage not in {"bareme", "calibrage"}:
        return _BASE_EXCHANGE(self, ident, stage, text, commit)
    data = parse_json(response_body(text, "json"))
    with database(self.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        dossier = self._dossier(conn, ident)
        result = _bareme(self, conn, dossier, data) if stage == "bareme" else _calibration(self, conn, dossier, data)
        if commit:
            self._record(conn, dossier, stage, data)
            conn.execute("UPDATE ui_rendu SET valide=0 WHERE dossier_id=?", (ident,))
        else:
            conn.rollback()
        return result


def _make_prompt(app, ident, stage, version=None, mode="echantillon"):
    # Active screens have one canonical prompt builder. Legacy routes remain
    # available for old integrations, but are never appended to active prompts.
    if stage in {'bareme', 'calibrage', 'correction', 'retour'}:
        from .workflow_prompts import make_prompt
        return make_prompt(app, ident, stage, version, mode)
    return _BASE_PROMPT(app, ident, stage, version, mode)


WorkflowApplication.state = _state
WorkflowApplication.draft = _draft
WorkflowApplication.exchange = _exchange
prompts.make_prompt = _make_prompt
