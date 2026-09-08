"""Edges of the Bikram Sambat layer: year boundaries, formatting, bad input."""

import datetime

import nepali_datetime as ndt
from django.test import SimpleTestCase

from nepal import dates


class ParseTests(SimpleTestCase):
    def test_every_separator_a_clerk_might_type(self):
        for raw in (
            "2082-05-17",
            "2082/05/17",
            "2082.05.17",
            "2082 05 17",
            "२०८२।०५।१७",
        ):
            self.assertEqual(dates.parse_bs(raw), ndt.date(2082, 5, 17))

    def test_single_digit_month_and_day(self):
        self.assertEqual(dates.parse_bs("2082-5-7"), ndt.date(2082, 5, 7))

    def test_surrounding_whitespace_is_ignored(self):
        self.assertEqual(dates.parse_bs("  2082-05-17 "), ndt.date(2082, 5, 17))

    def test_a_bs_date_passes_straight_through(self):
        bs = ndt.date(2082, 5, 17)
        self.assertIs(dates.parse_bs(bs), bs)

    def test_none_and_empty_are_refused(self):
        for bad in (None, "", "   "):
            with self.assertRaises(dates.InvalidBikramSambatDate):
                dates.parse_bs(bad)

    def test_out_of_range_parts_are_refused(self):
        for bad in (
            "2082-00-10",
            "2082-13-01",
            "2082-05-33",
            "9999-01-01",
            "1900-01-01",
        ):
            with self.assertRaises(dates.InvalidBikramSambatDate):
                dates.parse_bs(bad)

    def test_the_message_repeats_what_was_typed(self):
        with self.assertRaises(dates.InvalidBikramSambatDate) as caught:
            dates.parse_bs("१७-०५-२०८२")  # day-first, a common slip
        self.assertIn("१७-०५-२०८२", str(caught.exception))


class ConversionTests(SimpleTestCase):
    def test_ad_to_bs_accepts_date_datetime_and_iso_text(self):
        expected = ndt.date(2082, 5, 17)
        self.assertEqual(dates.ad_to_bs(datetime.date(2025, 9, 2)), expected)
        self.assertEqual(
            dates.ad_to_bs(datetime.datetime(2025, 9, 2, 14, 30)), expected
        )
        self.assertEqual(dates.ad_to_bs("2025-09-02"), expected)
        self.assertEqual(dates.ad_to_bs("२०२५-०९-०२"), expected)

    def test_round_trip_holds_across_a_whole_bs_month(self):
        for day in range(1, 32):
            bs = ndt.date(2082, 5, day)
            self.assertEqual(dates.ad_to_bs(bs.to_datetime_date()), bs)

    def test_new_year_crosses_in_mid_april(self):
        self.assertEqual(dates.format_bs(datetime.date(2025, 4, 13)), "2081-12-31")
        self.assertEqual(dates.format_bs(datetime.date(2025, 4, 14)), "2082-01-01")


class FormattingTests(SimpleTestCase):
    def test_none_formats_as_empty_text(self):
        self.assertEqual(dates.format_bs(None), "")
        self.assertEqual(dates.bs_display(None), "")
        self.assertEqual(dates.fiscal_year(None), "")

    def test_placeholders(self):
        ad = datetime.date(2025, 9, 2)
        self.assertEqual(dates.format_bs(ad, "{month_np}"), "भदौ")
        self.assertEqual(dates.format_bs(ad, "{month_en}"), "Bhadau")
        self.assertEqual(dates.format_bs(ad, "{weekday_np}"), "मंगलबार")
        self.assertEqual(dates.format_bs(ad, "{weekday_en}"), "Mangalbar")

    def test_devanagari_flag_only_changes_the_digits(self):
        ad = datetime.date(2025, 9, 2)
        self.assertEqual(dates.format_bs(ad, devanagari=True), "२०८२-०५-१७")
        self.assertEqual(dates.bs_display(ad, devanagari=False), "17 भदौ 2082")

    def test_the_nepali_week_starts_on_sunday(self):
        sunday = datetime.date(2025, 8, 31)
        self.assertEqual(dates.format_bs(sunday, "{weekday_np}"), "आइतबार")
        self.assertEqual(dates.format_bs(sunday, "{weekday_en}"), "Aaitabar")

    def test_digit_folding_round_trips(self):
        self.assertEqual(dates.ascii_digits(dates.devanagari_digits("2082")), "2082")
        self.assertEqual(dates.devanagari_digits(2082), "२०८२")
        self.assertEqual(dates.ascii_digits("no digits here"), "no digits here")


class FiscalYearTests(SimpleTestCase):
    def test_ashad_closes_and_shrawan_opens(self):
        self.assertEqual(dates.fiscal_year(ndt.date(2082, 3, 32)), "2081/82")
        self.assertEqual(dates.fiscal_year(ndt.date(2082, 4, 1)), "2082/83")

    def test_every_month_lands_in_the_right_year(self):
        for month in range(1, 4):
            self.assertEqual(dates.fiscal_year(ndt.date(2082, month, 1)), "2081/82")
        for month in range(4, 13):
            self.assertEqual(dates.fiscal_year(ndt.date(2082, month, 1)), "2082/83")

    def test_the_century_wraps_with_a_leading_zero(self):
        self.assertEqual(dates.fiscal_year(ndt.date(2099, 5, 1)), "2099/00")

    def test_bounds_are_inclusive_and_meet_end_to_end(self):
        start, end = dates.fiscal_year_bounds("2082/83")
        next_start, _ = dates.fiscal_year_bounds("2083/84")
        self.assertEqual(end + datetime.timedelta(days=1), next_start)
        self.assertEqual(dates.fiscal_year(start), "2082/83")
        self.assertEqual(dates.fiscal_year(end), "2082/83")

    def test_bounds_accept_devanagari_digits(self):
        self.assertEqual(
            dates.fiscal_year_bounds("२०८२/८३"), dates.fiscal_year_bounds("2082/83")
        )

    def test_recent_years_are_newest_first(self):
        years = dates.recent_fiscal_years(3, around=datetime.date(2025, 9, 2))
        self.assertEqual(years, ["2082/83", "2081/82", "2080/81"])

    def test_recent_years_before_shrawan_start_from_the_open_year(self):
        # Ashar 2082 is still fiscal 2081/82.
        years = dates.recent_fiscal_years(
            2, around=ndt.date(2082, 3, 15).to_datetime_date()
        )
        self.assertEqual(years, ["2081/82", "2080/81"])


class MonthBoundsTests(SimpleTestCase):
    def test_a_month_runs_to_the_day_before_the_next_one(self):
        start, end = dates.month_bounds(2082, 5)
        self.assertEqual(dates.format_bs(start), "2082-05-01")
        self.assertEqual(dates.format_bs(end), "2082-05-31")

    def test_chaitra_rolls_into_the_next_year(self):
        start, end = dates.month_bounds(2082, 12)
        self.assertEqual(dates.format_bs(start), "2082-12-01")
        self.assertEqual(dates.fiscal_year(end), "2082/83")
        self.assertEqual(
            dates.format_bs(end + datetime.timedelta(days=1)), "2083-01-01"
        )

    def test_ashad_can_run_to_thirty_two_days(self):
        _, end = dates.month_bounds(2083, 3)
        self.assertEqual(dates.format_bs(end), "2083-03-32")


class TodayTests(SimpleTestCase):
    def test_today_agrees_with_the_gregorian_clock(self):
        self.assertEqual(dates.today_bs().to_datetime_date(), datetime.date.today())
