"""The BS date field and the Devanagari-tolerant decimal field."""

import datetime
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.utils import translation

from nepal.forms import BikramSambatDateField, BikramSambatDateInput, NepaliDecimalField


class BikramSambatFieldTests(SimpleTestCase):
    def setUp(self):
        self.field = BikramSambatDateField(required=False)

    def test_every_accepted_spelling_normalises_to_one_string(self):
        for raw in ("2082-05-17", "2082/5/17", "२०८२।०५।१७", "2082.05.17"):
            self.assertEqual(self.field.clean(raw), "2082-05-17", raw)

    def test_empty_input_stays_empty_rather_than_becoming_a_date(self):
        for empty in ("", None):
            self.assertEqual(self.field.clean(empty), "")

    def test_an_impossible_date_is_a_form_error_not_a_crash(self):
        with self.assertRaises(ValidationError) as caught:
            self.field.clean("2082-13-45")
        self.assertEqual(caught.exception.code, "invalid_bs_date")
        self.assertIn("2082-13-45", str(caught.exception))

    def test_a_required_field_still_demands_a_value(self):
        with self.assertRaises(ValidationError):
            BikramSambatDateField().clean("")

    def test_overlong_input_is_rejected_before_parsing(self):
        with self.assertRaises(ValidationError):
            self.field.clean("2082-05-17-05-17")

    def test_to_ad_converts_and_tolerates_blank(self):
        self.assertEqual(
            BikramSambatDateField.to_ad("2082-05-17"), datetime.date(2025, 9, 2)
        )
        self.assertIsNone(BikramSambatDateField.to_ad(""))

    def test_its_label_says_bikram_sambat_in_the_active_language(self):
        field = BikramSambatDateField()
        with translation.override("en"):
            self.assertIn("BS", str(field.label))
        with translation.override("ne"):
            self.assertIn("बि.सं.", str(field.label))
        self.assertIn("YYYY-MM-DD", str(field.help_text))


class BikramSambatWidgetTests(SimpleTestCase):
    def test_it_asks_htmx_for_a_live_ad_preview(self):
        attrs = BikramSambatDateInput().attrs
        self.assertEqual(attrs["hx-get"], "/np/date-preview/")
        self.assertIn("changed", attrs["hx-trigger"])
        self.assertEqual(attrs["hx-target"], "next .bs-date-preview")

    def test_caller_attributes_win_over_the_defaults(self):
        attrs = BikramSambatDateInput(
            attrs={"class": "custom", "hx-get": "/elsewhere/"}
        ).attrs
        self.assertEqual(attrs["class"], "custom")
        self.assertEqual(attrs["hx-get"], "/elsewhere/")

    def test_it_renders_the_input_and_the_preview_slot(self):
        html = BikramSambatDateInput().render("date_bs", "2082-05-17")
        self.assertIn('name="date_bs"', html)
        self.assertIn('value="2082-05-17"', html)
        self.assertIn("bs-date-preview", html)


class NepaliDecimalFieldTests(SimpleTestCase):
    def setUp(self):
        self.field = NepaliDecimalField(max_digits=12, decimal_places=3, required=False)

    def test_devanagari_digits_are_accepted(self):
        self.assertEqual(self.field.clean("१२.५"), Decimal("12.5"))
        self.assertEqual(self.field.clean("१२३४"), Decimal("1234"))

    def test_thousands_separators_and_padding_are_accepted(self):
        self.assertEqual(self.field.clean(" 1,234.5 "), Decimal("1234.5"))
        self.assertEqual(self.field.clean("१,२३४.५"), Decimal("1234.5"))

    def test_plain_numbers_still_work(self):
        self.assertEqual(self.field.clean(Decimal("12.5")), Decimal("12.5"))
        self.assertEqual(self.field.clean(12.5), Decimal("12.5"))

    def test_blank_is_none_when_optional(self):
        self.assertIsNone(self.field.clean(""))

    def test_rubbish_is_a_form_error(self):
        with self.assertRaises(ValidationError):
            self.field.clean("बाह्र")

    def test_decimal_places_are_still_enforced(self):
        with self.assertRaises(ValidationError):
            self.field.clean("१.२३४५")


class FieldsInsideAFormTests(SimpleTestCase):
    """Both fields have to behave when Django drives them, not just the test."""

    class SlipForm(forms.Form):
        date_bs = BikramSambatDateField(required=False)
        qty = NepaliDecimalField(max_digits=12, decimal_places=3)

    def test_a_whole_form_cleans_devanagari_input(self):
        form = self.SlipForm({"date_bs": "२०८२।०५।१७", "qty": "१२.५"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["date_bs"], "2082-05-17")
        self.assertEqual(form.cleaned_data["qty"], Decimal("12.5"))

    def test_errors_land_on_the_right_field(self):
        form = self.SlipForm({"date_bs": "2082-13-45", "qty": "x"})
        self.assertFalse(form.is_valid())
        self.assertIn("date_bs", form.errors)
        self.assertIn("qty", form.errors)
