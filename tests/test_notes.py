from moteur.notes import NoteConfig, compute_final_note, compute_group_score, scale_score


def test_scale_score():
    assert scale_score(12, 15, 5) == 4


def test_group_mean():
    cfg = NoteConfig()
    assert compute_group_score([12, 15, 9], cfg) == 4


def test_final_rounding():
    cfg = NoteConfig(arrondi=0.5)
    assert compute_final_note(12.2, 3.1, cfg) == 15.5


def test_final_cap():
    cfg = NoteConfig()
    assert compute_final_note(18, 5, cfg) == 20
