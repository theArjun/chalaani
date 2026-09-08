"""The template filters, in both languages, including every branch of `|ago`."""

import datetime

from django.template import Context, Template
from django.test import RequestFactory, TestCase
from django.utils import timezone, translation

from nepal.context_processors import nepali_today
from nepal.templatetags import nepal as tags


class ScriptFollowsLanguageTests(TestCase):
    def test_a_bs_identifier_stays_ascii_in_both_languages(self):
        """`|bs` is the sortable identifier, not the reading of the date."""
        ad = datetime.date(2025, 9, 2)
        for language in ("ne", "en"):
            with translation.override(language):
                self.assertEqual(tags.bs(ad), "2082-05-17")

    def test_the_fiscal_year_filter(self):
        self.assertEqual(tags.fy(datetime.date(2025, 9, 2)), "2082/83")
        self.assertEqual(tags.fy(None), "")

    def test_dates_render_as_empty_when_there_is_no_date(self):
        self.assertEqual(tags.bs_date(None), "")
        self.assertEqual(tags.bs_date_long(None), "")
        self.assertEqual(tags.num(None), "")

    def test_quantities_lose_their_trailing_zeros(self):
        with translation.override("en"):
            self.assertEqual(tags.qty("12.500"), "12.5")
            self.assertEqual(tags.qty("12.000"), "12")
            self.assertEqual(tags.qty("0"), "0")
        with translation.override("ne"):
            self.assertEqual(tags.qty("12.000"), "१२")

    def test_money_always_groups_in_lakhs(self):
        with translation.override("en"):
            self.assertEqual(tags.money("1234567.5"), "12,34,567.50")
        with translation.override("ne"):
            self.assertEqual(tags.money("1234567.5"), "१२,३४,५६७.५०")

    def test_a_unit_label_falls_back_to_the_code_it_does_not_know(self):
        with translation.override("en"):
            self.assertEqual(tags.unit_label("bag"), "Bag / Sack")
            self.assertEqual(tags.unit_label("gross"), "gross")

    def test_status_chips_are_produced_for_the_four_statuses(self):
        for status in ("extracting", "draft", "verified", "billed"):
            self.assertEqual(tags.status_badge(status), f"chip chip-{status}")
        self.assertEqual(tags.status_badge(""), "chip chip-draft")

    def test_the_today_tags(self):
        from nepal import dates

        today = dates.today_bs()
        with translation.override("en"):
            self.assertEqual(
                tags.today_bs(), dates.format_bs(today, "{d} {month_en} {y}")
            )
        self.assertEqual(tags.current_fiscal_year(), dates.fiscal_year(today))


class RelativeTimeTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()

    def ago(self, value, language="en"):
        with translation.override(language):
            return tags.ago(value)

    def test_nothing_renders_as_nothing(self):
        self.assertEqual(tags.ago(None), "")
        self.assertEqual(tags.ago(""), "")

    def test_named_days(self):
        self.assertEqual(self.ago(self.today), "today")
        self.assertEqual(self.ago(self.today - datetime.timedelta(days=1)), "yesterday")
        self.assertEqual(self.ago(self.today + datetime.timedelta(days=1)), "tomorrow")

    def test_days_weeks_months_and_years(self):
        cases = {
            5: "5 days ago",
            29: "29 days ago",
            60: "2 months ago",
            364: "12 months ago",
            400: "1 year ago",
            800: "2 years ago",
        }
        for days, expected in cases.items():
            self.assertEqual(self.ago(self.today - datetime.timedelta(days=days)), expected)

    def test_the_future_reads_forwards(self):
        self.assertEqual(self.ago(self.today + datetime.timedelta(days=3)), "in 3 days")
        self.assertEqual(self.ago(self.today + datetime.timedelta(days=90)), "in 3 months")

    def test_a_timestamp_gets_minutes_and_hours(self):
        now = timezone.now()
        self.assertEqual(self.ago(now), "just now")
        self.assertEqual(self.ago(now - datetime.timedelta(minutes=1)), "1 minute ago")
        self.assertEqual(self.ago(now - datetime.timedelta(minutes=45)), "45 minutes ago")
        self.assertEqual(self.ago(now - datetime.timedelta(hours=1)), "1 hour ago")
        self.assertEqual(self.ago(now - datetime.timedelta(hours=5)), "5 hours ago")

    def test_a_timestamp_from_yesterday_is_named_not_counted(self):
        self.assertEqual(
            self.ago(timezone.now() - datetime.timedelta(days=1, hours=2)), "yesterday"
        )

    def test_nepali_says_the_same_thing_in_devanagari(self):
        cases = {
            self.today: "आज",
            self.today - datetime.timedelta(days=1): "हिजो",
            self.today - datetime.timedelta(days=5): "५ दिन अघि",
            self.today - datetime.timedelta(days=60): "२ महिना अघि",
            self.today - datetime.timedelta(days=400): "१ वर्ष अघि",
        }
        for value, expected in cases.items():
            self.assertEqual(self.ago(value, "ne"), expected)

    def test_nepali_counts_minutes_too(self):
        self.assertEqual(
            self.ago(timezone.now() - datetime.timedelta(minutes=5), "ne"), "५ मिनेट अघि"
        )

    def test_no_relative_phrase_ever_carries_ascii_digits_in_nepali(self):
        for days in (2, 45, 400):
            phrase = self.ago(self.today - datetime.timedelta(days=days), "ne")
            self.assertFalse(any(ch.isdigit() and ch.isascii() for ch in phrase), phrase)


class InTemplateTests(TestCase):
    """The filters have to survive being loaded by name from a template."""

    def render(self, template, context=None, language="ne"):
        with translation.override(language):
            return Template("{% load nepal %}" + template).render(Context(context or {}))

    def test_a_row_of_a_register_renders_in_nepali(self):
        rendered = self.render(
            "{{ d|bs_date }} · {{ a|money }} · {{ q|qty }} {{ u|unit_label }}",
            {"d": datetime.date(2025, 9, 2), "a": "1234567.5", "q": "12.500", "u": "bag"},
        )
        self.assertEqual(rendered, "१७ भदौ २०८२ · १२,३४,५६७.५० · १२.५ बोरा")

    def test_the_same_row_in_english_keeps_bikram_sambat(self):
        rendered = self.render(
            "{{ d|bs_date_long }} · {{ a|in_words }}",
            {"d": datetime.date(2025, 9, 2), "a": "1250.50"},
            language="en",
        )
        self.assertIn("Mangalbar, 17 Bhadau 2082", rendered)
        self.assertIn("fifty paisa only", rendered)

    def test_the_today_tags_render(self):
        rendered = self.render("{% today_bs %}|{% current_fiscal_year %}")
        self.assertIn("|", rendered)
        self.assertTrue(rendered.split("|")[0])


class ContextProcessorTests(TestCase):
    def test_it_offers_todays_bs_date_in_the_active_language(self):
        request = RequestFactory().get("/")
        with translation.override("ne"):
            context = nepali_today(request)
        self.assertRegex(context["today_bs_iso"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(context["current_fy"], r"^\d{4}/\d{2}$")
        self.assertFalse(
            any(ch.isdigit() and ch.isascii() for ch in context["today_bs"])
        )

    def test_english_gets_the_same_date_in_latin_script(self):
        request = RequestFactory().get("/")
        with translation.override("en"):
            context = nepali_today(request)
        self.assertTrue(any(ch.isdigit() for ch in context["today_bs"]))

    def test_it_tells_the_base_template_whether_tailwind_comes_from_a_cdn(self):
        self.assertIn("TAILWIND_CDN", nepali_today(RequestFactory().get("/")))
