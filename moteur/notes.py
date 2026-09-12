from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_FLOOR, ROUND_CEILING
from statistics import mean, median
from .validation import object_fields, number

ROUNDINGS = {'demi_superieur': ROUND_HALF_UP, 'pair': ROUND_HALF_EVEN,
             'inferieur': ROUND_FLOOR, 'superieur': ROUND_CEILING}
MODES = {'moyenne_camarades', 'mediane_camarades', 'moyenne_groupe', 'mediane_groupe', 'aucun'}


@dataclass(frozen=True)
class NoteConfig:
    note_individuelle_max: float = 15.0
    note_groupe_max: float = 5.0
    groupe_mode: str = 'moyenne_camarades'
    arrondi: float | None = 0.5
    note_finale_max: float = 20.0
    arrondi_mode: str = 'demi_superieur'
    individuel_arrondi: float | None = None
    groupe_arrondi: float | None = None
    absence: str = 'exclure'
    sans_camarades: str = 'zero'
    poids_individuel: float = 1.0
    poids_groupe: float = 1.0
    bonus: float = 0.0

    def __post_init__(self):
        for key in ('note_individuelle_max', 'note_finale_max'):
            number(getattr(self, key), key, positive=True)
        for key in ('note_groupe_max', 'poids_individuel', 'poids_groupe', 'bonus'):
            number(getattr(self, key), key)
        for key in ('arrondi', 'individuel_arrondi', 'groupe_arrondi'):
            if getattr(self, key) is not None:
                number(getattr(self, key), key, positive=True)
        for value, choices in ((self.groupe_mode, MODES), (self.arrondi_mode, ROUNDINGS),
                               (self.absence, {'exclure', 'zero'}),
                               (self.sans_camarades, {'zero', 'individuelle', 'erreur'})):
            if not isinstance(value, str) or value not in choices:
                raise ValueError(f'Option inconnue : {value}')


def _round_step(value, step, mode='demi_superieur'):
    if step is None:
        return float(value)
    quantum = Decimal(str(step))
    return float((Decimal(str(value)) / quantum).quantize(Decimal('1'), rounding=ROUNDINGS[mode]) * quantum)


def compute_raw_score(points):
    obtained, maximum = Decimal(0), Decimal(0)
    for score, max_score in points:
        number(score, 'points'); number(max_score, 'barème')
        if score > max_score:
            raise ValueError('Points supérieurs au barème')
        obtained += Decimal(str(score)); maximum += Decimal(str(max_score))
    return float(obtained), float(maximum)


def scale_score(score, source_max, target_max):
    number(score); number(source_max, 'barème source', positive=True); number(target_max)
    return float(min(Decimal(str(target_max)), Decimal(str(score)) / Decimal(str(source_max)) * Decimal(str(target_max))))


def compute_group_score(peer_scores, cfg):
    values = [number(v) for v in peer_scores]
    if cfg.groupe_mode == 'aucun' or not values:
        return 0.0
    base = median(values) if cfg.groupe_mode.startswith('mediane') else mean(values)
    result = scale_score(base, cfg.note_individuelle_max, cfg.note_groupe_max)
    return min(cfg.note_groupe_max, _round_step(result, cfg.groupe_arrondi, cfg.arrondi_mode))


def compute_final_note(note_individuelle, note_groupe, cfg):
    number(note_individuelle); number(note_groupe)
    d = lambda x: Decimal(str(x))
    note = d(note_individuelle)*d(cfg.poids_individuel) + d(note_groupe)*d(cfg.poids_groupe) + d(cfg.bonus)
    return min(cfg.note_finale_max, max(0., _round_step(min(d(cfg.note_finale_max), note), cfg.arrondi, cfg.arrondi_mode)))


def config_from_mapping(data):
    object_fields(data, {'note_individuelle', 'note_groupe', 'note_finale', 'absences'})
    individuel = object_fields(data.get('note_individuelle', {}), {'max', 'arrondi'})
    groupe = object_fields(data.get('note_groupe', {}), {'max', 'mode', 'arrondi', 'sans_camarades'})
    finale = object_fields(data.get('note_finale', {}), {'max', 'arrondi', 'arrondi_mode', 'poids_individuel', 'poids_groupe', 'bonus'})
    absences = object_fields(data.get('absences', {}), {'mode'})
    return NoteConfig(note_individuelle_max=individuel.get('max', 15),
        note_groupe_max=groupe.get('max', 5), groupe_mode=groupe.get('mode', 'moyenne_camarades'),
        arrondi=finale.get('arrondi', .5), note_finale_max=finale.get('max', 20),
        arrondi_mode=finale.get('arrondi_mode', 'demi_superieur'),
        individuel_arrondi=individuel.get('arrondi'), groupe_arrondi=groupe.get('arrondi'),
        absence=absences.get('mode', 'exclure'), sans_camarades=groupe.get('sans_camarades', 'zero'),
        poids_individuel=finale.get('poids_individuel', 1), poids_groupe=finale.get('poids_groupe', 1),
        bonus=finale.get('bonus', 0))
