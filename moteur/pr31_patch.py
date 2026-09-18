"""Fast four-step workflow: barème, iterative calibration, full correction, results."""
from __future__ import annotations

import json

from .db import database
from .gui_service import Application as BaseApplication, public_json, response_body
from .validation import array, number, object_fields, parse_json, string
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
        _set_meta(conn, _RETURNS_KEY.format(ident), combined)
    return {"enregistre": True}


def _bareme(self, conn, dossier, data):
    """Validate the final barème before preprocessing/corrigé exists."""
    result = BaseApplication._grid(self, conn, dossier, data)
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
        conn.execute("""INSERT INTO corrige(version_id,str_latex) VALUES(?,?)
            ON CONFLICT(version_id) DO UPDATE SET str_latex=excluded.str_latex""",
            (versions[version], latex))
    if seen != set(versions):
        missing = ", ".join(sorted(set(versions) - seen))
        raise ValueError(f"Corrigé manquant pour : {missing}")


def _calibration(self, conn, dossier, data):
    allowed = {"dossier", "revision", "pretraitement", "corriges", "corrections", "a_revoir", "moyenne_estimee"}
    object_fields(data, allowed, {"dossier", "revision", "corrections", "moyenne_estimee"})
    if data["dossier"] != dossier["id"] or data["revision"] != dossier["revision"]:
        raise ValueError("Cette réponse vise un autre dossier ou une ancienne grille.")

    had_copies = bool(conn.execute("SELECT 1 FROM ui_copie WHERE dossier_id=? LIMIT 1", (dossier["id"],)).fetchone())
    prep = pr20._read_preprocessing(conn, dossier["id"])
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

    corrections = array(data["corrections"], "corrections", True)
    refs = [string(c.get("reference"), "reference") for c in corrections if isinstance(c, dict)]
    if not 1 <= len(refs) <= 5 or len(set(refs)) != len(refs):
        raise ValueError("Le lot de calibrage doit contenir entre 1 et 5 copies distinctes.")

    current = {r["reference"] for r in conn.execute(
        "SELECT reference FROM ui_copie WHERE dossier_id=? AND echantillon=1", (dossier["id"],))}
    if had_copies and current and set(refs) != current:
        raise ValueError("Le JSON doit corriger exactement le lot affiché dans SmartCorrection.")

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
    mean = number(data["moyenne_estimee"], "moyenne estimée")
    if not 0 <= mean <= 20:
        raise ValueError("La moyenne estimée doit être comprise entre 0 et 20.")
    _set_meta(conn, _MEAN_KEY.format(dossier["id"]), str(mean))
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


def _bareme_prompt(app, ident):
    prefix, state = prompts._prefix(app, ident)
    d = state["dossier"]
    example = {
        "dossier": ident, "revision": d["revision"],
        "versions": [{"version": "A"}],
        "grilles": [{
            "nom": "Barème", "version": "A",
            "exercices": [{"numero": "1", "questions": [{"numero": "1", "items": [
                {"code": "E1Q1I1", "description": "Critère précis", "bareme_max": 1}
            ]}]}],
        }],
    }
    return prefix + """
OBJECTIF — construire le barème avec l'enseignant.
Analyse le sujet, les savoir-faire, les documents de référence et les copies jointes. Propose d'abord un barème argumenté et discute-le normalement avec l'enseignant. Ne rends PAS le JSON tant que l'enseignant n'a pas indiqué que le barème lui convient.
Pendant la discussion, tiens compte explicitement de ses décisions sur la sévérité, les erreurs de calcul, la rédaction, les équivalences, les symboles et les pénalités.
Quand l'enseignant valide le barème dans la conversation, rends alors uniquement un bloc JSON complet, sans texte autour, avec cette structure :
""" + public_json(example)


def _calibration_prompt(app, ident):
    prefix, state = prompts._prefix(app, ident)
    d = state["dossier"]
    copies = state.get("copies") or []
    selected = [c["reference"] for c in copies if c.get("echantillon")]
    first = not copies
    if first:
        target = "les cinq premières copies du paquet (ou toutes s'il y en a moins de cinq)"
    else:
        target = ", ".join(selected)
    returns = (state.get("calibrage") or {}).get("retours") or "Aucun ajustement encore."
    mean = (state.get("calibrage") or {}).get("moyenne_estimee")
    vigilance = ""
    if mean not in (None, ""):
        try:
            if float(mean) >= 14:
                vigilance = (" La moyenne estimée précédente est élevée : cherche particulièrement les petites erreurs de calcul, "
                             "notations imprécises, oublis de justification et défauts de rédaction, sans inventer d'erreur ni viser artificiellement une moyenne.")
        except ValueError:
            pass
    first_fields = """
Pour ce PREMIER lot seulement, le même JSON doit aussi contenir :
- pretraitement : inventaire COMPLET de toutes les copies du paquet, pages, versions et pages ignorées. Pour chaque copie : reference, numero (toujours null), version, pages ;
- corriges : tous les corrigés de référence, adaptés au format de sortie déjà choisi.
""" if first else """
Le prétraitement et les corrigés sont déjà enregistrés : ne les répète pas sauf si l'enseignant t'a explicitement demandé de les corriger.
"""
    return prefix + f"""
CALIBRAGE DE LA CORRECTION — même écran, boucle par lots.
Corrige exactement ce lot : {target}.
{first_fields}
Applique le barème validé et toutes les décisions pédagogiques suivantes, accumulées pendant le calibrage :
--- DÉCISIONS DE L'ENSEIGNANT ---
{returns}
--- FIN DES DÉCISIONS ---
{vigilance}
Donne aussi moyenne_estimee, ton estimation actuelle de la moyenne finale de la classe sur 20. Cette estimation est un signal de vigilance, jamais une cible : ne durcis ni n'assouplis artificiellement pour atteindre une moyenne.

Rends uniquement UN JSON complet :
{{
  "dossier": "{ident}",
  "revision": {d["revision"]},
  "pretraitement": {{"copies": [{{"reference": "C001", "numero": null, "version": "A", "pages": [1, 2]}}], "pages_ignorees": [], "absents": []}},
  "corriges": [{{"version": "A", "corrige_latex": "..."}}, ...],
  "corrections": [{{"reference": "C001", "items": [...], "annotations": [], "conseils": [], "commentaire_global": null, "a_verifier": []}}, ...],
  "a_revoir": [],
  "moyenne_estimee": 12.5
}}
Les champs pretraitement et corriges sont obligatoires au premier lot et facultatifs ensuite.
"""


def _make_prompt(app, ident, stage, version=None, mode="echantillon"):
    if stage == "bareme":
        return _bareme_prompt(app, ident)
    if stage == "calibrage":
        return _calibration_prompt(app, ident)
    if stage == "correction" and mode == "reste":
        base = _BASE_PROMPT(app, ident, stage, version, mode)
        state = app.state(ident)
        returns = (state.get("calibrage") or {}).get("retours")
        if returns:
            base += "\n\nDÉCISIONS FIGÉES PENDANT LE CALIBRAGE — applique-les à toutes les copies restantes :\n" + returns
        return base
    return _BASE_PROMPT(app, ident, stage, version, mode)


WorkflowApplication.state = _state
WorkflowApplication.draft = _draft
WorkflowApplication.exchange = _exchange
prompts.make_prompt = _make_prompt
