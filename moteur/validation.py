"""Small strict validators shared by imports and configuration (standard library only)."""
import json
import math
from pathlib import Path


def object_fields(value, allowed, required=(), where='objet'):
    if not isinstance(value, dict):
        raise ValueError(f'{where}: objet attendu')
    unknown = set(value) - set(allowed)
    missing = set(required) - set(value)
    if unknown or missing:
        raise ValueError(f'{where}: champs inconnus {sorted(unknown)}, manquants {sorted(missing)}')
    return value


def number(value, where='nombre', minimum=0, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{where}: nombre fini attendu')
    if value < minimum or (positive and value == 0):
        raise ValueError(f'{where}: valeur hors limites')
    return float(value)


def integer(value, where='identifiant', minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{where}: entier >= {minimum} attendu')
    return value


def string(value, where='texte', nullable=False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{where}: texte non vide attendu')
    return value


def array(value, where='liste', nonempty=False):
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f'{where}: liste {"non vide " if nonempty else ""}attendue')
    return value


def load_json(path):
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError(f'Clé JSON répétée : {key}')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f'Nombre JSON interdit : {value}')
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs, parse_constant=invalid)
