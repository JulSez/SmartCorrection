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


def _normalize_correction_items(corrections):
    """Accept the common AI alias 'code' but store the canonical 'item_code'."""
    normalized = []
    for correction in corrections:
        if not isinstance(correction, dict):
            normalized.append(correction)
            continue
        copy = dict(correction)
        items = []
        for item in copy.get("items", []):
            if not isinstance(item, dict):
                items.append(item)
                continue
            clean = dict(item)
            if "code" in clean:
                if "item_code" in clean and clean["item_code"] != clean["code"]:
                    raise ValueError("Un item contient code et item_code avec des valeurs différentes.")
                clean.setdefault("item_code", clean["code"])
                clean.pop("code", None)
            items.append(clean)
        copy["items"] = items
        normalized.append(copy)
    return normalized


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

    corrections = _normalize_correction_items(array(data["corrections"], "corrections", True))
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



def _correction_json_contract():
    return r"""
CONTRAT JSON STRICT POUR UNE CORRECTION
Respecte exactement ces types et ces noms de champs. N'ajoute aucun champ.

corrections est une liste d'objets. Chaque objet correction :
{
  "reference": "C001",
  "items": [
    {
      "item_code": "E1Q1I1",
      "points_obtenus": 1,
      "statut": "partiel",
      "commentaire": "Erreur de signe.",
      "annotation": null
    }
  ],
  "annotations": [
    {
      "item_code": "E1Q1I1",
      "page": 2,
      "texte": "Erreur ici.",
      "x": 0.42,
      "y": 0.31,
      "largeur": 0.18,
      "hauteur": 0.05,
      "type_annotation": "erreur"
    }
  ],
  "conseils": [
    {
      "texte": "Vérifier les signes avant de conclure.",
      "item_code": "E1Q1I1",
      "priorite": 1
    }
  ],
  "commentaire_global": "Ensemble correct mais calculs fragiles.",
  "a_verifier": ["Lecture du signe en page 2 à confirmer."]
}

Règles impératives :
- items : un objet par item du barème, exactement une fois. Utilise "item_code", jamais "code".
- points_obtenus : nombre JSON, jamais null, compris entre 0 et le maximum de l'item.
- statut : facultatif ; null ou exactement "acquis", "partiel", "non_acquis", "non_repondu".
- commentaire et annotation dans items : chaîne ou null. Si tous les points ne sont pas attribués, explique la perte de points dans commentaire ou annotation.
- annotations : liste d'OBJETS, jamais une liste de textes. Chaque objet exige item_code, page et texte. x, y, largeur, hauteur sont facultatifs ; s'ils sont fournis, ce sont des nombres entre 0 et 1. type_annotation est facultatif.
- conseils : liste d'OBJETS, jamais une liste de textes. Chaque objet exige texte ; item_code et priorite sont facultatifs. priorite, si présente, est un entier >= 1.
- commentaire_global : chaîne ou null.
- a_verifier : liste de CHAÎNES courtes, jamais une liste d'objets. Utilise-la seulement pour une incertitude non bloquante à relire par le professeur.
- a_revoir : liste d'objets {"reference":"C001","motif":"..."} pour une copie impossible à corriger complètement sans deviner. Ne mets alors pas cette copie dans corrections.
"""

def _preprocessing_json_contract():
    return r"""
CONTRAT JSON STRICT DU PRÉTRAITEMENT
pretraitement est un objet :
{
  "copies": [
    {
      "reference": "C001",
      "identite_lue": "17",
      "numero": null,
      "version": "A",
      "pages": [1, 2]
    }
  ],
  "pages_ignorees": [
    {"page": 3, "motif": "page blanche"}
  ],
  "absents": []
}

Règles impératives :
- reference : chaîne C001, C002, etc., unique.
- identite_lue : chaîne contenant exactement ce qui est lisible sur la copie (numéro écrit par l'élève, ou nom/prénom), ou null. N'invente rien.
- numero : toujours null dans la réponse IA ; l'association à la liste locale est faite ensuite par SmartCorrection et peut être corrigée par le professeur.
- version : chaîne correspondant à une version du sujet.
- pages : liste non vide d'entiers, dans l'ordre du paquet.
- pages_ignorees : liste d'OBJETS {"page": entier, "motif": chaîne}, jamais une liste de numéros ni de textes.
- absents : toujours [] ; l'IA ne déduit pas les absences.
"""

def _corriges_json_contract():
    return r"""
CONTRAT JSON STRICT DES CORRIGÉS
corriges est une liste d'objets :
[
  {
    "version": "A",
    "corrige_latex": "\\section*{Exercice 1} ...",
    "sujet_latex": "\\textit{Sujet joint en PDF.}"
  }
]
Règles impératives :
- version et corrige_latex sont obligatoires.
- sujet_latex est facultatif.
- corrige_latex contient seulement le corps LaTeX : pas de documentclass, begin{document} ni end{document}.
"""

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
    first_fields = ("""
Pour ce PREMIER lot seulement, le même JSON doit aussi contenir le prétraitement COMPLET du paquet et TOUS les corrigés de référence.
""" + _preprocessing_json_contract() + _corriges_json_contract()) if first else """
Le prétraitement et les corrigés sont déjà enregistrés : ne les répète pas sauf si l'enseignant t'a explicitement demandé de les corriger.
"""
    example_ref = selected[0] if selected else "C001"
    example = {
        "dossier": ident,
        "revision": d["revision"],
        "corrections": [{
            "reference": example_ref,
            "items": [{
                "item_code": "E1Q1I1",
                "points_obtenus": 1,
                "statut": "partiel",
                "commentaire": "Erreur de signe.",
                "annotation": None,
            }],
            "annotations": [{
                "item_code": "E1Q1I1",
                "page": 1,
                "texte": "Erreur ici.",
                "x": None, "y": None, "largeur": None, "hauteur": None,
                "type_annotation": None,
            }],
            "conseils": [{
                "texte": "Vérifier les signes.",
                "item_code": "E1Q1I1",
                "priorite": 1,
            }],
            "commentaire_global": "Calcul à sécuriser.",
            "a_verifier": [],
        }],
        "a_revoir": [],
        "moyenne_estimee": 12.5,
    }
    if first:
        example["pretraitement"] = {
            "copies": [{
                "reference": "C001",
                "identite_lue": "17",
                "numero": None,
                "version": "A",
                "pages": [1, 2],
            }],
            "pages_ignorees": [{"page": 3, "motif": "page blanche"}],
            "absents": [],
        }
        example["corriges"] = [{
            "version": "A",
            "corrige_latex": r"\section*{Exercice 1} ...",
            "sujet_latex": r"\textit{Sujet joint en PDF.}",
        }]
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

{_correction_json_contract()}

ENVELOPPE FINALE À RENDRE
Rends uniquement UN bloc JSON complet, sans commentaire autour.
Voici un EXEMPLE STRUCTUREL VALIDE pour ce lot ; remplace les valeurs par celles réellement lues/corrigées :
{public_json(example)}
{"Au premier lot, pretraitement et corriges sont obligatoires et doivent être complets." if first else "Pour ce lot, n'ajoute PAS pretraitement ni corriges : ils sont déjà enregistrés."}
Ne remplace jamais une structure inconnue par une supposition : le présent contrat décrit tous les champs autorisés.
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
        base += "\n\n" + _correction_json_contract()
        return base
    return _BASE_PROMPT(app, ident, stage, version, mode)


WorkflowApplication.state = _state
WorkflowApplication.draft = _draft
WorkflowApplication.exchange = _exchange
prompts.make_prompt = _make_prompt
