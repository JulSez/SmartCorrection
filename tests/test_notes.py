import unittest
from moteur.notes import NoteConfig, compute_final_note, compute_group_score, scale_score, config_from_mapping, _round_step

class NotesTests(unittest.TestCase):
    def test_scale_score(self):
        self.assertEqual(scale_score(12, 15, 5), 4)
    def test_group_mean(self):
        self.assertEqual(compute_group_score([12, 15, 9], NoteConfig()), 4)
    def test_final_rounding(self):
        self.assertEqual(compute_final_note(12.2, 3.1, NoteConfig()), 15.5)
    def test_final_cap(self):
        self.assertEqual(compute_final_note(18, 5, NoteConfig()), 20)
    def test_default_rounding_and_explicit_none(self):
        self.assertEqual(config_from_mapping({}).arrondi, .5)
        self.assertIsNone(config_from_mapping({'note_finale':{'arrondi':None}}).arrondi)
    def test_tie_and_post_round_cap(self):
        self.assertEqual(_round_step(14.25, .5), 14.5)
        self.assertEqual(_round_step(14.25, .5, 'pair'), 14)
        self.assertEqual(compute_final_note(20, 0, NoteConfig(note_finale_max=19.8)), 19.8)
    def test_decimal_total(self):
        self.assertEqual(compute_final_note(.1, .2, NoteConfig(arrondi=None)), .3)
    def test_invalid_config(self):
        for data in ({'typo':1}, {'note_groupe':{'mode':'typo'}}, {'note_finale':{'arrondi':0}},
                     {'note_individuelle':{'max':True}}, {'note_groupe':{'max':float('nan')}},
                     {'note_finale':{'arrondi_mode':'typo'}}, {'note_groupe':{'mode':[]}}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                config_from_mapping(data)
    def test_median(self):
        self.assertEqual(compute_group_score([0, 9, 15], NoteConfig(groupe_mode='mediane_camarades')), 3)
    def test_weights_bonus(self):
        self.assertEqual(compute_final_note(10, 4, NoteConfig(poids_individuel=.5, poids_groupe=2, bonus=1)),14)
