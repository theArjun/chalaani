"""Model behaviour: date syncing, totals, what blocks verification, scoping."""

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import translation

from chalani.models import Chalani, ChalaniItem, Item, Vendor, chalani_upload_path
from chalani.tests import PNG, make_org


class UploadPathTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()

    def test_photos_are_filed_under_the_organization_with_an_unguessable_name(self):
        chalani = Chalani(organization=self.org, created_by=self.user)
        path = chalani_upload_path(chalani, "IMG_2043.JPEG")
        self.assertTrue(path.startswith(f"chalani/{self.org.pk}/"))
        self.assertTrue(path.endswith(".jpeg"))
        self.assertNotIn("IMG_2043", path)

    def test_two_uploads_of_the_same_filename_never_collide(self):
        chalani = Chalani(organization=self.org, created_by=self.user)
        first = chalani_upload_path(chalani, "slip.png")
        second = chalani_upload_path(chalani, "slip.png")
        self.assertNotEqual(first, second)

    def test_a_missing_extension_falls_back_to_jpg(self):
        chalani = Chalani(organization=self.org, created_by=self.user)
        self.assertTrue(chalani_upload_path(chalani, "photo").endswith(".jpg"))

    def test_a_real_upload_lands_on_that_path(self):
        chalani = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            photo=SimpleUploadedFile("slip.png", PNG, content_type="image/png"),
        )
        self.assertTrue(chalani.photo.name.startswith(f"chalani/{self.org.pk}/"))


class VendorAndItemTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()

    def test_a_vendor_prints_its_nepali_name_when_it_has_one(self):
        vendor = Vendor.objects.create(
            organization=self.org, name="Himal Cement", name_np="हिमाल सिमेन्ट"
        )
        self.assertEqual(str(vendor), "हिमाल सिमेन्ट")
        self.assertEqual(
            str(Vendor.objects.create(organization=self.org, name="Everest Steel")),
            "Everest Steel",
        )

    def test_the_search_key_folds_both_names_and_the_pan(self):
        vendor = Vendor.objects.create(
            organization=self.org,
            name="  Himal   Cement  Udyog ",
            name_np="हिमाल सिमेन्ट",
            pan_no="६००२३८९१४",
        )
        self.assertIn("himal cement udyog", vendor.search_key)
        self.assertIn("600238914", vendor.search_key)

    def test_the_search_key_is_refreshed_on_rename(self):
        vendor = Vendor.objects.create(organization=self.org, name="Old Name")
        vendor.name = "New Name"
        vendor.save()
        self.assertIn("new name", vendor.search_key)
        self.assertNotIn("old name", vendor.search_key)

    def test_an_item_folds_however_its_unit_was_spelled(self):
        item = Item.objects.create(organization=self.org, name="Cement", unit="बोरा")
        self.assertEqual(item.unit, "bag")

    def test_an_unknown_unit_falls_back_to_pieces(self):
        item = Item.objects.create(organization=self.org, name="Odd", unit="mystery")
        self.assertEqual(item.unit, "pcs")

    def test_a_vendors_pan_is_validated_on_full_clean(self):
        vendor = Vendor(organization=self.org, name="Bad PAN", pan_no="123")
        with self.assertRaises(ValidationError):
            vendor.full_clean()

    def test_catalog_rows_never_leak_between_firms(self):
        other, _other_user = make_org("Other", "clerk_other")
        Vendor.objects.create(organization=other, name="Everest Steel")
        Vendor.objects.create(organization=self.org, name="Himal Cement")
        self.assertEqual(
            [v.name for v in Vendor.objects.for_org(self.org)], ["Himal Cement"]
        )


class DateSyncEdgeTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()

    def _make(self, **kwargs):
        return Chalani.objects.create(
            organization=self.org, created_by=self.user, **kwargs
        )

    def test_the_bs_string_wins_over_a_contradicting_ad_date(self):
        """The paper is the source of truth."""
        chalani = self._make(date_bs="2082-05-17", date=datetime.date(2001, 1, 1))
        self.assertEqual(chalani.date, datetime.date(2025, 9, 2))

    def test_devanagari_input_is_stored_in_ascii(self):
        self.assertEqual(self._make(date_bs="२०८२।०५।१७").date_bs, "2082-05-17")

    def test_a_loose_bs_string_is_tidied_on_save(self):
        self.assertEqual(self._make(date_bs="2082/5/7").date_bs, "2082-05-07")

    def test_no_date_at_all_leaves_the_fiscal_year_blank(self):
        chalani = self._make()
        self.assertEqual(chalani.date_bs, "")
        self.assertIsNone(chalani.date)
        self.assertEqual(chalani.fiscal_year, "")

    def test_an_unreadable_bs_string_never_guesses_a_gregorian_date(self):
        chalani = self._make(date_bs="2082-99-99")
        self.assertIsNone(chalani.date)
        self.assertEqual(chalani.fiscal_year, "")

    def test_the_fiscal_year_follows_the_date_when_it_is_corrected(self):
        chalani = self._make(date_bs="2082-03-31")
        self.assertEqual(chalani.fiscal_year, "2081/82")
        chalani.date_bs = "2082-04-01"
        chalani.save()
        self.assertEqual(chalani.fiscal_year, "2082/83")

    def test_the_nepali_reading_of_the_date_follows_the_language(self):
        chalani = self._make(date_bs="2082-05-17")
        self.assertEqual(chalani.date_bs_np, "१७ भदौ २०८२")

    def test_an_undated_chalani_shows_whatever_the_paper_said(self):
        chalani = self._make(date_bs="2082-99-99")
        self.assertEqual(chalani.date_bs_np, "2082-99-99")


class TotalsTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.chalani = Chalani.objects.create(
            organization=self.org, created_by=self.user, date_bs="2082-05-17"
        )

    def _line(self, **kwargs):
        kwargs.setdefault("description", "सिमेन्ट")
        kwargs.setdefault("qty", 10)
        return ChalaniItem.objects.create(chalani=self.chalani, **kwargs)

    def test_a_line_without_a_rate_has_no_amount(self):
        self.assertIsNone(self._line().amount)

    def test_an_amount_is_rounded_to_paisa(self):
        line = self._line(qty=Decimal("3.333"), rate=Decimal("7.77"))
        self.assertEqual(line.amount, Decimal("25.90"))

    def test_the_total_ignores_lines_that_have_no_rate(self):
        self._line(qty=10, rate=Decimal("870"))
        self._line(description="तार", qty=5)
        self.assertEqual(self.chalani.total_amount, Decimal("8700.00"))

    def test_a_chalani_with_no_priced_lines_totals_zero(self):
        self._line()
        self.assertEqual(self.chalani.total_amount, Decimal("0"))
        self.assertFalse(self.chalani.has_rates)

    def test_has_rates_notices_a_single_priced_line(self):
        self._line()
        self._line(description="तार", qty=1, rate=Decimal("120"))
        self.assertTrue(self.chalani.has_rates)

    def test_the_annotated_total_agrees_with_the_python_one(self):
        self._line(qty=10, rate=Decimal("870"))
        self._line(description="तार", qty=Decimal("15.5"), rate=Decimal("120"))
        annotated = Chalani.objects.with_totals().get(pk=self.chalani.pk)
        self.assertEqual(annotated.line_count, 2)
        self.assertEqual(annotated.total, self.chalani.total_amount)

    def test_a_line_folds_its_unit_on_save(self):
        self.assertEqual(self._line(unit="बोरा").unit, "bag")

    def test_lines_keep_the_order_they_were_written_in(self):
        self._line(description="third", line_no=3)
        self._line(description="first", line_no=1)
        self._line(description="second", line_no=2)
        self.assertEqual(
            [line.description for line in self.chalani.items.all()],
            ["first", "second", "third"],
        )

    def test_deleting_a_chalani_takes_its_lines_with_it(self):
        self._line()
        self.chalani.delete()
        self.assertFalse(ChalaniItem.objects.exists())


class MissingForVerificationTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.vendor = Vendor.objects.create(organization=self.org, name="Himal Cement")
        self.item = Item.objects.create(
            organization=self.org, name="Cement", unit="bag"
        )
        self.chalani = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            vendor=self.vendor,
            chalani_no="C/1204",
            date_bs="2082-05-17",
        )
        ChalaniItem.objects.create(
            chalani=self.chalani, item=self.item, description="सिमेन्ट", qty=10
        )

    def gaps(self):
        return [str(gap) for gap in self.chalani.missing_for_verification()]

    def test_a_complete_chalani_has_nothing_blocking_it(self):
        self.assertEqual(self.gaps(), [])

    def test_a_missing_supplier_is_reported(self):
        self.chalani.vendor = None
        with translation.override("en"):
            self.assertIn("no supplier chosen", self.gaps())

    def test_a_missing_number_is_reported(self):
        self.chalani.chalani_no = ""
        with translation.override("en"):
            self.assertIn("no chalani number", self.gaps())

    def test_a_missing_date_is_reported(self):
        self.chalani.date = None
        with translation.override("en"):
            self.assertIn("no date", self.gaps())

    def test_no_goods_at_all_is_reported(self):
        self.chalani.items.all().delete()
        with translation.override("en"):
            self.assertIn("no goods added", self.gaps())

    def test_an_unlinked_line_is_reported(self):
        self.chalani.items.update(item=None)
        with translation.override("en"):
            self.assertIn("some lines are not linked to the catalog", self.gaps())

    def test_a_blank_draft_reports_every_gap_at_once(self):
        blank = Chalani.objects.create(organization=self.org, created_by=self.user)
        with translation.override("en"):
            self.assertEqual(
                [str(gap) for gap in blank.missing_for_verification()],
                [
                    "no supplier chosen",
                    "no chalani number",
                    "no date",
                    "no goods added",
                ],
            )

    def test_the_reasons_are_translated(self):
        self.chalani.vendor = None
        with translation.override("ne"):
            self.assertIn("आपूर्तिकर्ता", " ".join(self.gaps()))


class StatusTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()

    def _make(self, status):
        return Chalani.objects.create(
            organization=self.org, created_by=self.user, status=status
        )

    def test_drafts_and_verified_chalani_are_editable(self):
        self.assertTrue(self._make(Chalani.Status.DRAFT).is_editable)
        self.assertTrue(self._make(Chalani.Status.VERIFIED).is_editable)

    def test_a_billed_or_still_reading_chalani_is_not(self):
        self.assertFalse(self._make(Chalani.Status.BILLED).is_editable)
        self.assertFalse(self._make(Chalani.Status.EXTRACTING).is_editable)

    def test_pending_review_is_everything_a_clerk_still_owes(self):
        self._make(Chalani.Status.DRAFT)
        self._make(Chalani.Status.EXTRACTING)
        self._make(Chalani.Status.VERIFIED)
        self.assertEqual(Chalani.objects.pending_review().count(), 2)

    def test_a_new_chalani_starts_as_a_draft(self):
        self.assertEqual(
            Chalani.objects.create(organization=self.org, created_by=self.user).status,
            Chalani.Status.DRAFT,
        )


class QuerySetTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()

    def _make(self, date_bs, **kwargs):
        return Chalani.objects.create(
            organization=self.org, created_by=self.user, date_bs=date_bs, **kwargs
        )

    def test_the_register_reads_newest_first(self):
        older = self._make("2082-05-01", chalani_no="older")
        newer = self._make("2082-05-17", chalani_no="newer")
        self.assertEqual([c.pk for c in Chalani.objects.all()], [newer.pk, older.pk])

    def test_a_fiscal_year_filter_covers_shrawan_to_ashad(self):
        self._make("2082-04-01")  # first day of 2082/83
        self._make("2083-03-32")  # last day of 2082/83
        self._make("2083-04-01")  # first day of 2083/84
        self.assertEqual(Chalani.objects.in_fiscal_year("2082/83").count(), 2)
        self.assertEqual(Chalani.objects.in_fiscal_year("2083/84").count(), 1)

    def test_no_fiscal_year_means_no_filtering(self):
        self._make("2082-05-17")
        self.assertEqual(Chalani.objects.in_fiscal_year("").count(), 1)

    def test_an_undated_chalani_belongs_to_no_fiscal_year(self):
        self._make("")
        self.assertEqual(Chalani.objects.in_fiscal_year("2082/83").count(), 0)


class StrTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()

    def test_a_numbered_chalani_prints_its_number_and_supplier(self):
        vendor = Vendor.objects.create(organization=self.org, name="Himal Cement")
        chalani = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            vendor=vendor,
            chalani_no="C/1204",
        )
        self.assertEqual(str(chalani), "C/1204 · Himal Cement")

    def test_an_unnumbered_draft_falls_back_to_its_id(self):
        chalani = Chalani.objects.create(organization=self.org, created_by=self.user)
        with translation.override("en"):
            self.assertEqual(str(chalani), f"#{chalani.pk} · unknown supplier")

    def test_a_line_prints_what_the_paper_said(self):
        chalani = Chalani.objects.create(organization=self.org, created_by=self.user)
        line = ChalaniItem.objects.create(
            chalani=chalani, description="सिमेन्ट", qty=Decimal("10.000"), unit="bag"
        )
        self.assertEqual(str(line), "सिमेन्ट — 10.000 bag")
