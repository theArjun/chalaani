"""The identifiers a Nepali firm actually keys in: PAN, phone, vehicle plate."""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from nepal.validators import (
    normalise_phone,
    validate_nepali_phone,
    validate_pan,
    validate_vehicle_no,
)


class PanTests(SimpleTestCase):
    def test_nine_digits_pass(self):
        validate_pan("600238914")

    def test_devanagari_digits_pass(self):
        validate_pan("६००२३८९१४")

    def test_separators_are_ignored(self):
        validate_pan("600-238 914")

    def test_blank_is_allowed_because_the_field_is_optional(self):
        for empty in ("", None):
            validate_pan(empty)

    def test_wrong_length_is_refused(self):
        for bad in ("12345678", "1234567890", "6002389AB"):
            with self.assertRaises(ValidationError) as caught:
                validate_pan(bad)
            self.assertEqual(caught.exception.code, "invalid_pan")


class PhoneTests(SimpleTestCase):
    def test_mobiles(self):
        for good in ("9812345678", "९८१२३४५६७८", "+977 9812345678", "977-9712345678"):
            validate_nepali_phone(good)

    def test_landlines(self):
        for good in ("01-4567890", "014567890", "0561234567"):
            validate_nepali_phone(good)

    def test_blank_is_allowed(self):
        validate_nepali_phone("")

    def test_obvious_rubbish_is_refused(self):
        for bad in ("12345", "not a phone", "98123"):
            with self.assertRaises(ValidationError) as caught:
                validate_nepali_phone(bad)
            self.assertEqual(caught.exception.code, "invalid_phone")

    def test_normalise_strips_country_code_and_separators(self):
        self.assertEqual(normalise_phone("+977 98-1234 5678"), "9812345678")
        self.assertEqual(normalise_phone("9812345678"), "9812345678")
        self.assertEqual(normalise_phone("९८१२३४५६७८"), "9812345678")
        self.assertEqual(normalise_phone(""), "")

    def test_normalise_keeps_a_short_number_that_merely_starts_with_977(self):
        """`977…` is only a country code when what follows is a whole number."""
        self.assertEqual(normalise_phone("9771234"), "9771234")


class VehicleTests(SimpleTestCase):
    def test_plates_in_either_script(self):
        for good in (
            "बा १२ ख ३४५६",
            "Ba 12 Kha 3456",
            "प्रदेश ३-०१-००१ च ०४३४",
            "KO-1-PA-1234",
        ):
            validate_vehicle_no(good)

    def test_surrounding_space_is_tolerated(self):
        validate_vehicle_no("  बा १२ ख ३४५६  ")

    def test_blank_is_allowed(self):
        validate_vehicle_no("")

    def test_stray_punctuation_is_refused(self):
        for bad in ("बा@१२ ख", "<script>alert(1)</script>", "!!!"):
            with self.assertRaises(ValidationError) as caught:
                validate_vehicle_no(bad)
            self.assertEqual(caught.exception.code, "invalid_vehicle")

    def test_a_plate_is_never_longer_than_the_column(self):
        with self.assertRaises(ValidationError):
            validate_vehicle_no("ब" * 40)
