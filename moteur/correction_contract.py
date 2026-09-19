"""Field vocabulary shared by the importer and the active AI instructions."""
from .validation import array, object_fields

STATUSES = ('acquis', 'partiel', 'non_acquis', 'non_repondu')
# Each field has a human-readable type and an optional flag. This is vocabulary,
# not a second validator: semantic checks stay in the transactional importer.
FIELDS = {
    'correction': {
        'reference': ('référence C001', False), 'items': ('liste d’items', False),
        'annotations': ('liste d’annotations, [] par défaut', True),
        'conseils': ('liste de conseils, [] par défaut', True),
        'commentaire_global': ('texte ou null, null par défaut', True),
        'a_verifier': ('liste de textes : incertitudes non bloquantes', True),
    },
    'item': {
        'item_code': ('code exact du barème', False), 'points_obtenus': ('nombre entre 0 et le maximum', False),
        'commentaire': ('erreur en quelques mots, sinon null', True),
        'annotation': ('texte ou null, sans répéter commentaire', True),
        'statut': ('null ou ' + '/'.join(STATUSES), True),
    },
    'conseil': {'texte': ('texte court', False), 'item_code': ('code du barème ou null', True),
                'priorite': ('entier >= 1 ou null', True)},
    'annotation': {'item_code': ('code du barème', False), 'page': ('page physique de la copie, entier >= 1', False),
                   'texte': ('texte court', False), 'x': ('nombre 0..1 ou null', True),
                   'y': ('nombre 0..1 ou null', True), 'largeur': ('nombre 0..1 ou null', True),
                   'hauteur': ('nombre 0..1 ou null', True), 'type_annotation': ('texte ou null', True)},
    'a_revoir': {'reference': ('référence C001', False), 'motif': ('texte expliquant le blocage', False)},
}


def check_fields(value, kind, where):
    fields = FIELDS[kind]
    return object_fields(value, fields, [k for k, (_, optional) in fields.items() if not optional], where)


def describe():
    lines = ['FORMAT DES OBJETS — champs marqués ? facultatifs ; aucun autre champ.']
    for kind, fields in FIELDS.items():
        lines.append(kind + ' : ' + '; '.join(k + ('?' if optional else '') + ' = ' + desc
                                             for k, (desc, optional) in fields.items()) + '.')
    lines.append('Coordonnées : fournir x et y ensemble ; dimensions seulement avec une position ; le rectangle reste dans la page.')
    return '\n'.join(lines)


def normalize_corrections(value):
    """Compatibility alias, identical for calibration and full correction."""
    result = []
    for i, correction in enumerate(array(value, 'corrections')):
        where = f'corrections[{i}]'
        check_fields(correction, 'correction', where)
        items = []
        for j, item in enumerate(array(correction['items'], where+'.items', True)):
            if not isinstance(item, dict):
                raise ValueError(f'{where}.items[{j}]: objet attendu')
            item = dict(item)
            if 'code' in item:
                if 'item_code' in item and item['item_code'] != item['code']:
                    raise ValueError(f'{where}.items[{j}]: code et item_code différents')
                item['item_code'] = item.pop('code')
            items.append(item)
        result.append(dict(correction, items=items))
    return result
