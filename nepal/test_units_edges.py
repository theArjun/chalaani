"""Unit folding — the step that makes item-wise reports add up."""

from django.test import SimpleTestCase

from nepal import units


class CatalogTests(SimpleTestCase):
    def test_codes_are_unique(self):
        self.assertEqual(len(units.UNIT_CODES), len(set(units.UNIT_CODES)))

    def test_every_code_has_a_label_in_both_scripts(self):
        for code in units.UNIT_CODES:
            self.assertTrue(units.UNIT_LABELS_NP[code])
            self.assertTrue(units.UNIT_LABELS_EN[code])

    def test_choices_line_up_with_the_codes(self):
        self.assertEqual([code for code, _ in units.UNIT_CHOICES], units.UNIT_CODES)

    def test_every_code_folds_onto_itself(self):
        for code in units.UNIT_CODES:
            self.assertEqual(units.normalise_unit(code), code)

    def test_every_label_folds_back_onto_its_code(self):
        for code, np_label, en_label, _aliases in units.UNITS:
            self.assertEqual(units.normalise_unit(np_label), code, np_label)
            self.assertEqual(units.normalise_unit(en_label), code, en_label)

    def test_every_declared_alias_folds_onto_its_code(self):
        for code, _np, _en, aliases in units.UNITS:
            for alias in aliases:
                self.assertEqual(units.normalise_unit(alias), code, alias)


class NormalisationTests(SimpleTestCase):
    def test_the_many_ways_to_write_a_sack(self):
        for raw in ("Bora", "बोरा", "bags", "sack", "BAG", " bag ", "bora."):
            self.assertEqual(units.normalise_unit(raw), "bag", raw)

    def test_dots_and_spaces_are_ignored(self):
        for raw in ("sq.ft", "sq ft", "SQ. FT.", "वर्ग फिट"):
            self.assertEqual(units.normalise_unit(raw), "sqft", raw)

    def test_nepali_plurals_are_folded(self):
        self.assertEqual(units.normalise_unit("बोराहरु"), "bag")
        self.assertEqual(units.normalise_unit("बोराहरू"), "bag")

    def test_english_plurals_are_folded(self):
        self.assertEqual(units.normalise_unit("rolls"), "roll")
        self.assertEqual(units.normalise_unit("cartons"), "carton")

    def test_anything_unrecognised_falls_back_to_pieces(self):
        for raw in (None, "", "  ", "something odd", "मन"):
            self.assertEqual(units.normalise_unit(raw), "pcs", repr(raw))

    def test_the_fallback_is_caller_controlled(self):
        self.assertEqual(units.normalise_unit("mystery", default="kg"), "kg")

    def test_a_number_never_becomes_a_unit(self):
        self.assertEqual(units.normalise_unit("12"), "pcs")


class LabelTests(SimpleTestCase):
    def test_labels_follow_the_requested_script(self):
        self.assertEqual(units.unit_label("bag"), "बोरा")
        self.assertEqual(units.unit_label("bag", devanagari=False), "Bag / Sack")

    def test_an_unknown_code_is_echoed_back_rather_than_hidden(self):
        self.assertEqual(units.unit_label("gross"), "gross")
        self.assertEqual(units.unit_label("gross", devanagari=False), "gross")
