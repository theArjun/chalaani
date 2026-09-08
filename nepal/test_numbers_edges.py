"""Money and quantity rendering, including the cases that come off a bad slip."""

from decimal import Decimal

from django.test import SimpleTestCase

from nepal import numbers


class GroupingTests(SimpleTestCase):
    def test_the_first_comma_falls_after_three_digits_then_every_two(self):
        cases = {
            "0": "0.00",
            "1": "1.00",
            "999": "999.00",
            "1000": "1,000.00",
            "99999": "99,999.00",
            "100000": "1,00,000.00",
            "1234567.5": "12,34,567.50",
            "10000000": "1,00,00,000.00",
            "120000000": "12,00,00,000.00",
            "123456789012": "1,23,45,67,89,012.00",
        }
        for raw, expected in cases.items():
            self.assertEqual(numbers.group_indian(raw), expected, raw)

    def test_negatives_keep_the_sign_outside_the_grouping(self):
        self.assertEqual(numbers.group_indian("-1234567.5"), "-12,34,567.50")

    def test_decimal_places_are_configurable(self):
        self.assertEqual(numbers.group_indian("1234.567", decimals=0), "1,235")
        self.assertEqual(numbers.group_indian("1234.567", decimals=3), "1,234.567")

    def test_halves_round_up_the_way_a_ledger_expects(self):
        self.assertEqual(numbers.group_indian("0.005"), "0.01")
        self.assertEqual(numbers.group_indian("2.345"), "2.35")

    def test_devanagari_digits_and_stray_commas_are_accepted(self):
        self.assertEqual(numbers.group_indian("१२३४५६७.५"), "12,34,567.50")
        self.assertEqual(numbers.group_indian("12,34,567.50"), "12,34,567.50")
        self.assertEqual(numbers.group_indian("  1234 "), "1,234.00")

    def test_unreadable_input_becomes_zero_rather_than_an_exception(self):
        junk = (None, "", "क्ष", "12.34.56", "Rs 1200", [], float("nan"), float("inf"))
        for value in junk:
            self.assertEqual(numbers.group_indian(value), "0.00", repr(value))

    def test_a_non_finite_number_never_escapes_into_a_template(self):
        for value in (float("nan"), float("-inf"), "NaN", "Infinity"):
            self.assertEqual(numbers.format_amount(value), "0.00", repr(value))
            self.assertEqual(numbers.amount_in_words_en(value), "zero rupees only")

    def test_decimals_and_floats_are_both_accepted(self):
        self.assertEqual(numbers.group_indian(Decimal("1234567.5")), "12,34,567.50")
        self.assertEqual(numbers.group_indian(1234567.5), "12,34,567.50")

    def test_format_amount_adds_script_and_prefix(self):
        self.assertEqual(numbers.format_amount("1234567.5"), "12,34,567.50")
        self.assertEqual(
            numbers.format_amount("1234567.5", devanagari=True), "१२,३४,५६७.५०"
        )
        self.assertEqual(
            numbers.format_amount("1250", prefix="रू. ", devanagari=True), "रू. १,२५०.००"
        )


class WordsNepaliTests(SimpleTestCase):
    def test_zero(self):
        self.assertEqual(numbers.amount_in_words_np("0"), "शून्य रुपैयाँ मात्र")

    def test_paisa_are_spelled_out_only_when_present(self):
        self.assertEqual(
            numbers.amount_in_words_np("1250"), "एक हजार दुई सय पचास रुपैयाँ मात्र"
        )
        self.assertEqual(
            numbers.amount_in_words_np("1250.50"),
            "एक हजार दुई सय पचास रुपैयाँ पचास पैसा मात्र",
        )

    def test_the_south_asian_scale(self):
        self.assertIn("लाख", numbers.amount_in_words_np("1234567"))
        self.assertIn("करोड", numbers.amount_in_words_np("12345678"))
        self.assertIn("अरब", numbers.amount_in_words_np("1234567890"))

    def test_negative_amounts_are_marked(self):
        self.assertTrue(numbers.amount_in_words_np("-100").startswith("ऋणात्मक"))

    def test_the_currency_words_can_be_swapped(self):
        self.assertEqual(
            numbers.amount_in_words_np("5", currency="रुपियाँ"), "पाँच रुपियाँ मात्र"
        )


class WordsEnglishTests(SimpleTestCase):
    def test_lakh_and_crore_not_million(self):
        text = numbers.amount_in_words_en("1234567")
        self.assertTrue(text.startswith("twelve lakh"))
        self.assertNotIn("million", text)
        self.assertIn("crore", numbers.amount_in_words_en("12345678"))

    def test_tens_are_hyphenated(self):
        self.assertEqual(numbers.amount_in_words_en("34"), "thirty-four rupees only")
        self.assertEqual(numbers.amount_in_words_en("20"), "twenty rupees only")

    def test_paisa_and_sign(self):
        self.assertEqual(
            numbers.amount_in_words_en("1250.50"),
            "one thousand two hundred fifty rupees fifty paisa only",
        )
        self.assertTrue(numbers.amount_in_words_en("-1").startswith("minus"))

    def test_rounding_reaches_the_words(self):
        self.assertEqual(
            numbers.amount_in_words_en("0.994"), "zero rupees ninety-nine paisa only"
        )
        self.assertEqual(numbers.amount_in_words_en("0.999"), "one rupees only")
