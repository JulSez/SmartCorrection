from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import Iterable, Mapping


@dataclass(frozen=True)
class NoteConfig:
    note_individuelle_max: float = 15.0
    note_groupe_max: float = 5.0
    groupe_mode: str = "moyenne_camarades"
    arrondi: float | None = 0.5
    note_finale_max: float = 20.0


def _round_step(value: float, step: float | None) -> float:
    if not step:
        return value
    return round(value / step) * step


def compute_raw_score(points: Iterable[tuple[float, float]]) -> tuple[float, float]:
    """Return (points_obtenus, points_max)."""
    obtained = 0.0
    maximum = 0.0
    for score, max_score in points:
        obtained += float(score)
        maximum += float(max_score)
    return obtained, maximum


def scale_score(score: float, source_max: float, target_max: float) -> float:
    if source_max <= 0:
        return 0.0
    return max(0.0, min(target_max, score / source_max * target_max))


def compute_group_score(peer_scores: Iterable[float], cfg: NoteConfig) -> float:
    values = [float(v) for v in peer_scores]
    if not values:
        return 0.0

    if cfg.groupe_mode == "mediane_camarades":
        base = median(values)
    else:
        base = mean(values)

    return scale_score(base, cfg.note_individuelle_max, cfg.note_groupe_max)


def compute_final_note(
    note_individuelle: float,
    note_groupe: float,
    cfg: NoteConfig,
) -> float:
    note = min(cfg.note_finale_max, max(0.0, note_individuelle + note_groupe))
    return _round_step(note, cfg.arrondi)


def config_from_mapping(data: Mapping[str, object]) -> NoteConfig:
    individuel = data.get("note_individuelle", {}) or {}
    groupe = data.get("note_groupe", {}) or {}
    finale = data.get("note_finale", {}) or {}

    return NoteConfig(
        note_individuelle_max=float(individuel.get("max", 15.0)),
        note_groupe_max=float(groupe.get("max", 5.0)),
        groupe_mode=str(groupe.get("mode", "moyenne_camarades")),
        arrondi=(None if finale.get("arrondi") is None else float(finale.get("arrondi", 0.5))),
        note_finale_max=float(finale.get("max", 20.0)),
    )
