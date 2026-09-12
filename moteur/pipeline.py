from __future__ import annotations

import argparse
import json
from pathlib import Path

from .db import DEFAULT_DB, init_db
from .import_correction import import_correction_json
from .import_evaluation import import_evaluation_json
from .notes import config_from_mapping, compute_final_note, compute_group_score

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_init_db(args: argparse.Namespace) -> int:
    path = init_db(args.db)
    print(f"Base initialisée : {path}")
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    data = _load_json(args.config)
    cfg = config_from_mapping(data)
    peer_scores = [float(v) for v in args.peer]
    group = compute_group_score(peer_scores, cfg)
    final = compute_final_note(float(args.individual), group, cfg)
    print(json.dumps({
        "note_individuelle": float(args.individual),
        "note_groupe": group,
        "note_finale": final,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_import_correction(args: argparse.Namespace) -> int:
    correction_id = import_correction_json(args.file, args.db)
    print(f"Correction importée : id={correction_id}")
    return 0


def cmd_import_evaluation(args: argparse.Namespace) -> int:
    sujet_id = import_evaluation_json(args.file, args.db)
    print(f"Évaluation importée : sujet_id={sujet_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="smartcorrection")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="Initialiser la base SQLite")
    p_init.add_argument("--db", default=str(DEFAULT_DB))
    p_init.set_defaults(func=cmd_init_db)

    p_note = sub.add_parser("note", help="Tester le moteur de note")
    p_note.add_argument("--config", default=str(ROOT / "configs" / "exemple.json"))
    p_note.add_argument("--individual", type=float, required=True)
    p_note.add_argument("--peer", type=float, nargs="*", default=[])
    p_note.set_defaults(func=cmd_note)

    p_import = sub.add_parser("import-correction", help="Importer une correction JSON dans SQLite")
    p_import.add_argument("file", help="Chemin du fichier JSON de correction")
    p_import.add_argument("--db", default=str(DEFAULT_DB))
    p_import.set_defaults(func=cmd_import_correction)

    p_eval = sub.add_parser("import-evaluation", help="Importer sujet, versions, corrigés et grille")
    p_eval.add_argument("file", help="Chemin du fichier JSON d'évaluation")
    p_eval.add_argument("--db", default=str(DEFAULT_DB))
    p_eval.set_defaults(func=cmd_import_evaluation)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
