from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import connect


def import_evaluation_json(path: str | Path, db_path: str | Path) -> int:
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    sujet = data["sujet"]

    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO sujet
            (classe, chapitres, type, titre, date_evaluation, config_notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                sujet["classe"],
                sujet.get("chapitres"),
                sujet.get("type"),
                sujet.get("titre"),
                sujet.get("date_evaluation"),
                json.dumps(sujet.get("config_notes"), ensure_ascii=False)
                if sujet.get("config_notes") is not None
                else None,
            ),
        )
        sujet_id = int(cur.lastrowid)

        version_ids: dict[str, int] = {}
        for version in data.get("versions", []):
            cur = conn.execute(
                "INSERT INTO version (sujet_id, version, str_latex) VALUES (?, ?, ?)",
                (sujet_id, version["version"], version["str_latex"]),
            )
            version_id = int(cur.lastrowid)
            version_ids[str(version["version"])] = version_id
            if version.get("corrige_latex") is not None:
                conn.execute(
                    "INSERT INTO corrige (version_id, str_latex) VALUES (?, ?)",
                    (version_id, version["corrige_latex"]),
                )

        grid = data["grille"]
        grid_version_id = None
        if grid.get("version") is not None:
            grid_version_id = version_ids[str(grid["version"])]

        cur = conn.execute(
            "INSERT INTO grille (sujet_id, version_id, nom, total_points) VALUES (?, ?, ?, ?)",
            (sujet_id, grid_version_id, grid.get("nom"), None),
        )
        grille_id = int(cur.lastrowid)

        total = 0.0
        for ex_order, ex in enumerate(grid.get("exercices", []), start=1):
            cur = conn.execute(
                "INSERT INTO exercice (grille_id, numero, titre, ordre) VALUES (?, ?, ?, ?)",
                (grille_id, str(ex["numero"]), ex.get("titre"), ex_order),
            )
            exercice_id = int(cur.lastrowid)

            for q_order, q in enumerate(ex.get("questions", []), start=1):
                cur = conn.execute(
                    "INSERT INTO question (exercice_id, numero, texte, ordre) VALUES (?, ?, ?, ?)",
                    (exercice_id, str(q["numero"]), q.get("texte"), q_order),
                )
                question_id = int(cur.lastrowid)

                for i_order, item in enumerate(q.get("items", []), start=1):
                    max_points = float(item["bareme_max"])
                    conn.execute(
                        """
                        INSERT INTO item
                        (question_id, code, description, bareme_max, ordre, regle_correction)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            question_id,
                            item["code"],
                            item["description"],
                            max_points,
                            i_order,
                            item.get("regle_correction"),
                        ),
                    )
                    total += max_points

        conn.execute("UPDATE grille SET total_points = ? WHERE id = ?", (total, grille_id))

    return sujet_id
