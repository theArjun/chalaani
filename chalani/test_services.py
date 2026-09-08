"""Matching and draft-filling — the step that decides what a human still owes.

The rule under all of it: a wrong link is more expensive than an unlinked
draft, because every later report adds up by the link.
"""

import datetime
from decimal import Decimal

from django.test import TestCase

from chalani.models import Chalani, ChalaniItem, Item, Vendor
from chalani.services import (
    MATCH_CUTOFF,
    apply_extraction,
    match_item,
    match_vendor,
    next_line_no,
)
from chalani.tests import make_org
from extraction.schema import ChalaniExtraction, ExtractedItem


class VendorMatchingTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.vendor = Vendor.objects.create(
            organization=self.org,
            name="Himal Cement Udyog",
            name_np="हिमाल सिमेन्ट उद्योग",
            pan_no="600238914",
        )

    def test_an_exact_name_matches(self):
        self.assertEqual(match_vendor(self.org, name="Himal Cement Udyog"), self.vendor)

    def test_case_and_spacing_do_not_matter(self):
        self.assertEqual(
            match_vendor(self.org, name="  himal   CEMENT udyog "), self.vendor
        )

    def test_the_pan_beats_the_name_every_time(self):
        Vendor.objects.create(organization=self.org, name="Himal Cement Udyog Pvt")
        self.assertEqual(
            match_vendor(self.org, name="Something Else", pan="600238914"), self.vendor
        )

    def test_a_pan_in_devanagari_digits_still_matches(self):
        self.assertEqual(match_vendor(self.org, pan="६००२३८९१४"), self.vendor)

    def test_an_unknown_pan_falls_back_to_the_name(self):
        self.assertEqual(
            match_vendor(self.org, name="Himal Cement Udyog", pan="999999999"),
            self.vendor,
        )

    def test_a_longer_legal_name_on_the_next_slip_still_matches(self):
        self.assertEqual(
            match_vendor(self.org, name="Himal Cement Udyog Pvt. Ltd."), self.vendor
        )

    def test_a_small_typo_is_forgiven(self):
        self.assertEqual(match_vendor(self.org, name="Himal Cemant Udyog"), self.vendor)

    def test_a_different_supplier_is_never_guessed(self):
        for stranger in ("Everest Steel Traders", "Nepal Bitumen", "श्री राम हार्डवेयर"):
            self.assertIsNone(match_vendor(self.org, name=stranger), stranger)

    def test_two_branches_of_one_supplier_ask_a_human_instead_of_picking_one(self):
        Vendor.objects.create(
            organization=self.org, name="Shree Ram Hardware Biratnagar"
        )
        Vendor.objects.create(organization=self.org, name="Shree Ram Hardware Pokhara")
        self.assertIsNone(match_vendor(self.org, name="Shree Ram Hardware"))

    def test_a_branch_name_still_matches_when_only_one_could_be_meant(self):
        branch = Vendor.objects.create(
            organization=self.org, name="Shree Ram Hardware Biratnagar"
        )
        self.assertEqual(match_vendor(self.org, name="Shree Ram Hardware"), branch)

    def test_a_retired_supplier_is_not_matched(self):
        self.vendor.is_active = False
        self.vendor.save()
        self.assertIsNone(match_vendor(self.org, name="Himal Cement Udyog"))
        self.assertIsNone(match_vendor(self.org, pan="600238914"))

    def test_matching_never_crosses_a_firm_boundary(self):
        other, _user = make_org("Other", "clerk_other")
        self.assertIsNone(match_vendor(other, name="Himal Cement Udyog"))
        self.assertIsNone(match_vendor(other, pan="600238914"))

    def test_nothing_to_go_on_matches_nothing(self):
        self.assertIsNone(match_vendor(self.org))
        self.assertIsNone(match_vendor(self.org, name="", name_np="", pan=""))

    def test_an_empty_catalog_matches_nothing(self):
        Vendor.objects.all().delete()
        self.assertIsNone(match_vendor(self.org, name="Himal Cement Udyog"))

    def test_the_cutoff_is_high_enough_to_keep_two_real_suppliers_apart(self):
        self.assertGreaterEqual(MATCH_CUTOFF, 0.8)
        Vendor.objects.create(organization=self.org, name="Everest Steel Traders")
        self.assertIsNone(match_vendor(self.org, name="Everest Cement Traders"))


class ItemMatchingTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.item = Item.objects.create(
            organization=self.org,
            name="Cement OPC 50kg",
            name_np="सिमेन्ट ओ.पि.सि. ५० के.जी.",
            unit="bag",
        )

    def test_the_devanagari_description_matches(self):
        self.assertEqual(
            match_item(self.org, description="सिमेन्ट ओ.पि.सि. ५० के.जी."), self.item
        )

    def test_the_romanised_description_matches(self):
        self.assertEqual(
            match_item(self.org, description_en="Cement OPC 50kg"), self.item
        )

    def test_an_unrelated_line_stays_unlinked(self):
        self.assertIsNone(match_item(self.org, description="बाँध्ने तार"))

    def test_a_retired_item_is_not_matched(self):
        self.item.is_active = False
        self.item.save()
        self.assertIsNone(match_item(self.org, description="Cement OPC 50kg"))

    def test_matching_never_crosses_a_firm_boundary(self):
        other, _user = make_org("Other", "clerk_other")
        self.assertIsNone(match_item(other, description="Cement OPC 50kg"))


class ApplyExtractionTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.chalani = Chalani.objects.create(
            organization=self.org, created_by=self.user
        )

    def apply(self, **fields):
        apply_extraction(self.chalani, ChalaniExtraction(**fields))
        self.chalani.save()
        self.chalani.refresh_from_db()
        return self.chalani

    def test_an_empty_reading_leaves_an_empty_draft_rather_than_failing(self):
        chalani = self.apply()
        self.assertEqual(chalani.chalani_no, "")
        self.assertEqual(chalani.items.count(), 0)
        self.assertEqual(
            chalani.missing_for_verification()[0], chalani.missing_for_verification()[0]
        )

    def test_an_ad_only_slip_fills_the_bs_mirror(self):
        chalani = self.apply(date_ad="2025-09-02")
        self.assertEqual(chalani.date, datetime.date(2025, 9, 2))
        self.assertEqual(chalani.date_bs, "2082-05-17")

    def test_a_bs_date_wins_over_the_models_own_ad_reading(self):
        chalani = self.apply(date_bs="2082-05-17", date_ad="1999-01-01")
        self.assertEqual(chalani.date, datetime.date(2025, 9, 2))

    def test_an_unreadable_ad_date_is_dropped_rather_than_raised(self):
        chalani = self.apply(date_ad="०२/०९/२०२५")
        self.assertIsNone(chalani.date)

    def test_an_unreadable_bs_date_is_kept_for_a_human_to_fix(self):
        chalani = self.apply(date_bs="2082-99-99")
        self.assertEqual(chalani.date_bs, "2082-99-99")
        self.assertIsNone(chalani.date)

    def test_the_loose_notes_are_gathered_into_remarks(self):
        chalani = self.apply(
            destination="Balaju site", driver_name="Ram Bahadur", remarks="half load"
        )
        self.assertEqual(chalani.remarks, "Balaju site · Ram Bahadur · half load")

    def test_overlong_readings_are_trimmed_to_fit_their_columns(self):
        chalani = self.apply(
            chalani_no="C/" + "9" * 80,
            vehicle_no="बा " * 40,
            received_by="र" * 200,
            remarks="x" * 500,
        )
        self.assertEqual(len(chalani.chalani_no), 50)
        self.assertEqual(len(chalani.vehicle_no), 30)
        self.assertEqual(len(chalani.received_by), 100)
        self.assertEqual(len(chalani.remarks), 300)

    def test_lines_are_numbered_in_the_order_they_were_read(self):
        chalani = self.apply(
            items=[
                ExtractedItem(description="first"),
                ExtractedItem(description="second"),
                ExtractedItem(description="third"),
            ]
        )
        self.assertEqual(
            [(line.line_no, line.description) for line in chalani.items.all()],
            [(1, "first"), (2, "second"), (3, "third")],
        )

    def test_a_line_with_no_quantity_is_kept_at_zero_for_a_human(self):
        chalani = self.apply(items=[ExtractedItem(description="सिमेन्ट")])
        line = chalani.items.get()
        self.assertEqual(line.qty, Decimal("0.000"))

    def test_a_reading_with_neither_text_nor_quantity_is_dropped(self):
        chalani = self.apply(items=[ExtractedItem(description="")])
        self.assertEqual(chalani.items.count(), 0)

    def test_quantities_and_rates_are_stored_at_the_columns_precision(self):
        chalani = self.apply(
            items=[ExtractedItem(description="तार", qty=15.5, rate=120.456)]
        )
        line = chalani.items.get()
        self.assertEqual(line.qty, Decimal("15.500"))
        self.assertEqual(line.rate, Decimal("120.46"))

    def test_an_overlong_description_is_trimmed(self):
        chalani = self.apply(items=[ExtractedItem(description="सि" * 300, qty=1)])
        self.assertEqual(len(chalani.items.get().description), 200)

    def test_lines_a_clerk_already_typed_are_never_replaced(self):
        ChalaniItem.objects.create(
            chalani=self.chalani, description="typed by hand", qty=1, line_no=1
        )
        chalani = self.apply(items=[ExtractedItem(description="from the AI", qty=9)])
        self.assertEqual(
            [line.description for line in chalani.items.all()], ["typed by hand"]
        )

    def test_a_supplier_a_clerk_already_chose_is_never_replaced(self):
        chosen = Vendor.objects.create(organization=self.org, name="Chosen By Hand")
        Vendor.objects.create(organization=self.org, name="Himal Cement Udyog")
        self.chalani.vendor = chosen
        self.chalani.save()
        chalani = self.apply(vendor_name="Himal Cement Udyog")
        self.assertEqual(chalani.vendor, chosen)

    def test_a_vendor_the_register_does_not_know_leaves_the_link_empty(self):
        chalani = self.apply(vendor_name="Brand New Supplier")
        self.assertIsNone(chalani.vendor)
        self.assertEqual(chalani.remarks, "")

    def test_remarks_a_clerk_typed_are_never_replaced(self):
        self.chalani.remarks = "mine"
        self.chalani.save()
        chalani = self.apply(remarks="the AI's")
        self.assertEqual(chalani.remarks, "mine")


class NextLineNoTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.chalani = Chalani.objects.create(
            organization=self.org, created_by=self.user
        )

    def test_the_first_line_is_one(self):
        self.assertEqual(next_line_no(self.chalani), 1)

    def test_it_continues_past_the_highest_line_even_with_gaps(self):
        ChalaniItem.objects.create(
            chalani=self.chalani, description="a", qty=1, line_no=7
        )
        self.assertEqual(next_line_no(self.chalani), 8)

    def test_unnumbered_lines_do_not_confuse_it(self):
        ChalaniItem.objects.create(
            chalani=self.chalani, description="a", qty=1, line_no=0
        )
        self.assertEqual(next_line_no(self.chalani), 1)


class DecimalReadingTests(TestCase):
    """Numbers come off a slip in whatever shape the model read them."""

    def setUp(self):
        self.org, self.user = make_org()
        self.chalani = Chalani.objects.create(organization=self.org, created_by=self.user)

    def line_from(self, **item_fields):
        apply_extraction(
            self.chalani, ChalaniExtraction(items=[ExtractedItem(**item_fields)])
        )
        self.chalani.save()
        return self.chalani.items.get()

    def test_a_quantity_that_is_not_a_number_becomes_zero_for_a_human_to_fix(self):
        line = self.line_from(description="सिमेन्ट", qty=float("nan"))
        self.assertEqual(line.qty, Decimal("0.000"))

    def test_an_infinite_quantity_is_refused_the_same_way(self):
        line = self.line_from(description="सिमेन्ट", qty=float("inf"))
        self.assertEqual(line.qty, Decimal("0.000"))

    def test_a_rate_that_cannot_be_read_is_left_empty_rather_than_guessed(self):
        line = self.line_from(description="सिमेन्ट", qty=1, rate=float("nan"))
        self.assertIsNone(line.rate)
        self.assertIsNone(line.amount)


class RawNumberReadingTests(TestCase):
    """`_decimal` is what stands between a slip's text and a numeric column."""

    def test_it_reads_the_shapes_a_slip_produces(self):
        from chalani.services import _decimal

        self.assertEqual(_decimal("१२.५"), Decimal("12.500"))
        self.assertEqual(_decimal("1,234"), Decimal("1234.000"))
        self.assertEqual(_decimal(" 12 "), Decimal("12.000"))
        self.assertEqual(_decimal(870, places="0.01"), Decimal("870.00"))

    def test_anything_it_cannot_read_is_left_empty(self):
        from chalani.services import _decimal

        for junk in (None, "", "बाह्र", "12.34.56", "n/a", float("nan"), float("inf")):
            self.assertIsNone(_decimal(junk), repr(junk))
