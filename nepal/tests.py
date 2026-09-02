import datetime

from django.test import SimpleTestCase

from nepal import dates, numbers, units


class BikramSambatTests(SimpleTestCase):
    def test_parses_ascii_and_devanagari(self):
        self.assertEqual(dates.bs_to_ad("2082-05-17"), datetime.date(2025, 9, 2))
        self.assertEqual(dates.bs_to_ad("२०८२।०५।१७"), datetime.date(2025, 9, 2))
        self.assertEqual(dates.bs_to_ad("2082/5/17"), datetime.date(2025, 9, 2))

    def test_round_trip(self):
        ad = datetime.date(2025, 9, 2)
        self.assertEqual(dates.format_bs(ad), "2082-05-17")
        self.assertEqual(dates.bs_display(ad), "१७ भदौ २०८२")

    def test_rejects_impossible_dates(self):
        with self.assertRaises(dates.InvalidBikramSambatDate):
            dates.parse_bs("2082-13-01")
        with self.assertRaises(dates.InvalidBikramSambatDate):
            dates.parse_bs("not a date")

    def test_fiscal_year_starts_in_shrawan(self):
        self.assertEqual(dates.fiscal_year(dates.bs_to_ad("2082-03-31")), "2081/82")
        self.assertEqual(dates.fiscal_year(dates.bs_to_ad("2082-04-01")), "2082/83")

    def test_fiscal_year_bounds_cover_the_year(self):
        start, end = dates.fiscal_year_bounds("2082/83")
        self.assertEqual(dates.format_bs(start), "2082-04-01")
        self.assertEqual(dates.fiscal_year(end), "2082/83")
        self.assertEqual(dates.fiscal_year(end + datetime.timedelta(days=1)), "2083/84")


class NumberTests(SimpleTestCase):
    def test_lakh_crore_grouping(self):
        self.assertEqual(numbers.group_indian("1234567.5"), "12,34,567.50")
        self.assertEqual(numbers.group_indian("999"), "999.00")
        self.assertEqual(numbers.group_indian("120000000"), "12,00,00,000.00")

    def test_words(self):
        self.assertEqual(
            numbers.amount_in_words_np("1250.50"),
            "एक हजार दुई सय पचास रुपैयाँ पचास पैसा मात्र",
        )
        self.assertTrue(numbers.amount_in_words_en("1234567").startswith("twelve lakh"))

    def test_devanagari_digits(self):
        self.assertEqual(numbers.devanagari_digits("2082-05-17"), "२०८२-०५-१७")
        self.assertEqual(numbers.ascii_digits("२०८२"), "2082")


class UnitTests(SimpleTestCase):
    def test_folds_spellings_onto_one_code(self):
        for raw in ["Bora", "बोरा", "bags", "sack", "BAG"]:
            self.assertEqual(units.normalise_unit(raw), "bag")
        self.assertEqual(units.normalise_unit("sq.ft"), "sqft")
        self.assertEqual(units.normalise_unit(None), "pcs")
        self.assertEqual(units.normalise_unit("something odd"), "pcs")
