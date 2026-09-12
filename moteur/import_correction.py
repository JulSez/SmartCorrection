from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import connect


def import_correction_json(path: str | Path, db_path: str | Path) -> int:
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))

    copie_id = int(data["copie_id"])
    grille_id = int(data["grille_id"])

    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO correction (copie_id, grille_id, commentaire_global) VALUES (?, ?, ?)",
            (copie_id, grille_id, data.get("commentaire_global")),
        )
        correction_id = int(cur.lastrowid)

        total = 0.0
        for entry in data.get("items", []):
            item = conn.execute(
                "SELECT id, bareme_max FROM item WHERE code = ?",
                (entry["item_code"],),
            ).fetchone()
            if item is None:
                raise ValueError(f"Item inconnu : {entry['item_code']}")

            points = float(entry["points_obtenus"])
            max_points = float(item["bareme_max"])
            if not 0.0 <= points <= max_points:
                raise ValueError(
                    f"Score invalide pour {entry['item_code']} : {points} / {max_points}"
                )

            conn.execute(
                """
                INSERT INTO correction_item
                (correction_id, item_id, points_obtenus, statut, annotation, commentaire)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    correction_id,
                    int(item["id"]),
                    points,
                    entry.get("statut"),
                    entry.get("annotation"),
                    entry.get("commentaire"),
                ),
            )
            total += points

        for advice in data.get("conseils", []):
            item_id = None
            code = advice.get("item_code")
            if code:
                row = conn.execute("SELECT id FROM item WHERE code = ?", (code,)).fetchone()
                if row is None:
                    raise ValueError(f"Item inconnu dans conseil : {code}")
                item_id = int(row["id"])

            conn.execute(
                "INSERT INTO conseil (correction_id, item_id, texte, priorite) VALUES (?, ?, ?, ?)",
                (correction_id, item_id, advice["texte"], advice.get("priorite")),
            )

        conn.execute(
            "UPDATE correction SET note_brute = ? WHERE id = ?",
            (total, correction_id),
        )

    return correction_id
