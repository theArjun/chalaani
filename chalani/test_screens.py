"""The screens: dashboard, register filters, CSV, reports, catalog, transitions."""

from decimal import Decimal
from unittest import mock

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from chalani.models import Chalani, ChalaniItem, Item, Vendor
from chalani.tests import PNG, make_org
from orgs.models import Membership


def messages_in(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


class RegisterFilterTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.himal = Vendor.objects.create(
            organization=self.org, name="Himal Cement", name_np="हिमाल सिमेन्ट"
        )
        self.everest = Vendor.objects.create(
            organization=self.org, name="Everest Steel"
        )
        self.cement = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            vendor=self.himal,
            chalani_no="C/1204",
            date_bs="2082-05-17",
            vehicle_no="बा १२ ख ३४५६",
            received_by="रमेश",
            status=Chalani.Status.VERIFIED,
        )
        ChalaniItem.objects.create(
            chalani=self.cement, description="सिमेन्ट", qty=10, unit="bag", rate=870
        )
        self.steel = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            vendor=self.everest,
            chalani_no="S/77",
            date_bs="2081-05-17",
        )
        ChalaniItem.objects.create(
            chalani=self.steel, description="डन्डी", qty=2, unit="ton"
        )
        self.client.force_login(self.user)
        self.url = reverse("chalani:register")

    def rows(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_free_text_finds_a_chalani_number(self):
        body = self.rows(q="C/1204")
        self.assertIn("C/1204", body)
        self.assertNotIn("S/77", body)

    def test_free_text_finds_a_devanagari_number(self):
        self.assertIn("C/1204", self.rows(q="C/१२०४"))

    def test_free_text_finds_a_vehicle_a_receiver_and_a_supplier(self):
        for needle in ("बा १२ ख", "रमेश", "Himal", "हिमाल"):
            self.assertIn("C/1204", self.rows(q=needle), needle)

    def test_free_text_reaches_into_the_goods_lines(self):
        self.assertIn("C/1204", self.rows(q="सिमेन्ट"))

    def test_a_search_that_matches_nothing_shows_nothing(self):
        body = self.rows(q="zzzz")
        self.assertNotIn("C/1204", body)
        self.assertNotIn("S/77", body)

    def test_the_status_filter(self):
        self.assertIn("C/1204", self.rows(status="verified"))
        self.assertNotIn("C/1204", self.rows(status="draft"))

    def test_the_supplier_filter(self):
        body = self.rows(vendor=str(self.himal.pk))
        self.assertIn("C/1204", body)
        self.assertNotIn("S/77", body)

    def test_a_nonsense_supplier_filter_is_ignored_rather_than_erroring(self):
        self.assertIn("C/1204", self.rows(vendor="not-a-number"))

    def test_the_fiscal_year_filter(self):
        self.assertIn("C/1204", self.rows(fy="2082/83"))
        self.assertNotIn("C/1204", self.rows(fy="2081/82"))

    def test_a_bs_date_range(self):
        body = self.rows(**{"from": "2082-01-01", "to": "2082-12-30"})
        self.assertIn("C/1204", body)
        self.assertNotIn("S/77", body)

    def test_an_unreadable_date_filter_warns_and_keeps_the_page_up(self):
        response = self.client.get(self.url, {"from": "2082-99-99"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("2082-99-99" in m for m in messages_in(response)))
        self.assertContains(response, "C/1204")

    def test_filters_combine(self):
        body = self.rows(status="verified", vendor=str(self.himal.pk), fy="2082/83")
        self.assertIn("C/1204", body)
        self.assertNotIn("S/77", body)

    def test_the_totals_line_counts_what_is_shown(self):
        response = self.client.get(self.url, {"vendor": str(self.himal.pk)})
        self.assertEqual(response.context["totals"]["count"], 1)
        self.assertEqual(response.context["totals"]["amount"], Decimal("8700"))

    def test_another_firms_chalani_is_never_listed(self):
        other, other_user = make_org("Other", "clerk_other")
        Chalani.objects.create(
            organization=other, created_by=other_user, chalani_no="SECRET/1"
        )
        self.assertNotIn("SECRET/1", self.rows())


class ExportCsvTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        vendor = Vendor.objects.create(organization=self.org, name="Himal Cement")
        chalani = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            vendor=vendor,
            chalani_no="C/1204",
            date_bs="2082-05-17",
        )
        ChalaniItem.objects.create(
            chalani=chalani, description="सिमेन्ट", qty=10, rate=870
        )
        self.client.force_login(self.user)
        self.url = reverse("chalani:export_csv")

    def body(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return response, response.content.decode("utf-8-sig")

    def test_it_downloads_as_a_csv_file(self):
        response, _body = self.body()
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("chalani-register.csv", response["Content-Disposition"])

    def test_it_is_utf8_with_a_bom_so_excel_reads_devanagari(self):
        response, _body = self.body()
        self.assertIn("utf-8-sig", response["Content-Type"])

    def test_a_row_carries_both_calendars_and_the_total(self):
        _response, body = self.body()
        self.assertIn("2082-05-17", body)
        self.assertIn("2025-09-02", body)
        self.assertIn("2082/83", body)
        self.assertIn("C/1204", body)
        self.assertIn("8700", body)

    def test_it_obeys_the_same_filters_as_the_register(self):
        _response, body = self.body(status="verified")
        self.assertNotIn("C/1204", body)

    def test_it_never_exports_another_firms_rows(self):
        other, other_user = make_org("Other", "clerk_other")
        Chalani.objects.create(
            organization=other, created_by=other_user, chalani_no="SECRET/1"
        )
        _response, body = self.body()
        self.assertNotIn("SECRET/1", body)


class DashboardTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.client.force_login(self.user)

    def test_an_empty_register_still_renders(self):
        response = self.client.get(reverse("chalani:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["counts"]["total"], 0)

    def test_it_counts_the_current_fiscal_year_by_status(self):
        from nepal import dates as npdates

        today = npdates.today_bs()
        date_bs = f"{today.year}-{today.month:02d}-{today.day:02d}"
        vendor = Vendor.objects.create(organization=self.org, name="Himal Cement")
        for status in (
            Chalani.Status.DRAFT,
            Chalani.Status.VERIFIED,
            Chalani.Status.BILLED,
        ):
            chalani = Chalani.objects.create(
                organization=self.org,
                created_by=self.user,
                vendor=vendor,
                date_bs=date_bs,
                status=status,
                chalani_no=f"C/{status}",
            )
            ChalaniItem.objects.create(
                chalani=chalani, description="सिमेन्ट", qty=1, rate=100
            )

        response = self.client.get(reverse("chalani:dashboard"))
        counts = response.context["counts"]
        self.assertEqual(counts["total"], 3)
        self.assertEqual(counts["drafts"], 1)
        self.assertEqual(counts["verified"], 1)
        self.assertEqual(counts["billed"], 1)
        self.assertEqual(response.context["amount"], Decimal("300"))
        self.assertEqual(response.context["vendor_count"], 1)

    def test_a_firmless_user_is_asked_to_register_a_firm(self):
        loner = make_org("Throwaway", "loner")[1]
        loner.memberships.all().delete()
        loner.active_organization = None
        loner.save()
        self.client.force_login(loner)
        self.assertRedirects(
            self.client.get(reverse("chalani:dashboard")), reverse("orgs:create")
        )


class VendorReportTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.vendor = Vendor.objects.create(organization=self.org, name="Himal Cement")
        self.item = Item.objects.create(
            organization=self.org, name="Cement", unit="bag"
        )
        chalani = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            vendor=self.vendor,
            chalani_no="C/1",
            date_bs="2082-05-17",
        )
        ChalaniItem.objects.create(
            chalani=chalani, item=self.item, description="सिमेन्ट", qty=10, rate=870
        )
        self.client.force_login(self.user)
        self.url = reverse("chalani:vendor_report")

    def test_totals_are_grouped_by_supplier_and_by_item(self):
        response = self.client.get(self.url, {"fy": "2082/83"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["grand_total"], Decimal("8700"))
        self.assertEqual(list(response.context["rows"])[0]["amount"], Decimal("8700"))
        self.assertEqual(
            list(response.context["item_rows"])[0]["total_qty"], Decimal("10")
        )

    def test_the_period_shown_is_the_fiscal_year_asked_for(self):
        response = self.client.get(self.url, {"fy": "2082/83"})
        start, end = response.context["period"]
        self.assertEqual(start.isoformat(), "2025-07-17")
        self.assertGreater(end, start)

    def test_another_fiscal_year_is_empty_rather_than_wrong(self):
        response = self.client.get(self.url, {"fy": "2080/81"})
        self.assertEqual(response.context["grand_total"], 0)

    def test_it_never_reports_another_firms_totals(self):
        other, other_user = make_org("Other", "clerk_other")
        vendor = Vendor.objects.create(organization=other, name="Everest Steel")
        chalani = Chalani.objects.create(
            organization=other,
            created_by=other_user,
            vendor=vendor,
            date_bs="2082-05-17",
        )
        ChalaniItem.objects.create(
            chalani=chalani, description="डन्डी", qty=5, rate=1000
        )
        response = self.client.get(self.url, {"fy": "2082/83"})
        self.assertEqual(response.context["grand_total"], Decimal("8700"))


class CatalogScreenTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.other, self.other_user = make_org("Other", "clerk_other")
        self.vendor = Vendor.objects.create(
            organization=self.org, name="Himal Cement", name_np="हिमाल सिमेन्ट"
        )
        self.foreign = Vendor.objects.create(
            organization=self.other, name="Everest Steel"
        )
        self.client.force_login(self.user)

    def test_creating_a_supplier_stamps_the_current_firm(self):
        response = self.client.post(
            reverse("chalani:vendor_create"),
            {
                "name": "Nepal Bitumen",
                "name_np": "",
                "pan_no": "600238914",
                "phone": "9812345678",
                "address": "",
                "district": "",
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("chalani:vendor_list"))
        self.assertEqual(
            Vendor.objects.get(name="Nepal Bitumen").organization, self.org
        )

    def test_an_invalid_pan_keeps_the_form_open(self):
        response = self.client.post(
            reverse("chalani:vendor_create"), {"name": "Bad PAN", "pan_no": "12"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vendor.objects.filter(name="Bad PAN").exists())

    def test_editing_a_supplier(self):
        self.client.post(
            reverse("chalani:vendor_edit", args=[self.vendor.pk]),
            {
                "name": "Himal Cement Udyog",
                "name_np": "हिमाल सिमेन्ट",
                "pan_no": "",
                "phone": "",
                "address": "",
                "district": "",
                "is_active": "on",
            },
        )
        self.vendor.refresh_from_db()
        self.assertEqual(self.vendor.name, "Himal Cement Udyog")

    def test_another_firms_supplier_cannot_be_opened_or_edited(self):
        url = reverse("chalani:vendor_edit", args=[self.foreign.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"name": "Hijacked"}).status_code, 404)

    def test_the_supplier_list_searches_both_scripts_and_the_pan(self):
        self.vendor.pan_no = "600238914"
        self.vendor.save()
        for needle in ("Himal", "हिमाल", "600238914"):
            response = self.client.get(reverse("chalani:vendor_list"), {"q": needle})
            self.assertContains(response, "Himal Cement", msg_prefix=needle)
        self.assertNotContains(
            self.client.get(reverse("chalani:vendor_list"), {"q": "zzz"}),
            "Himal Cement",
        )

    def test_the_supplier_list_never_shows_another_firms_rows(self):
        self.assertNotContains(
            self.client.get(reverse("chalani:vendor_list")), "Everest Steel"
        )

    def test_an_htmx_search_returns_only_the_rows(self):
        response = self.client.get(
            reverse("chalani:vendor_list"),
            {"q": "Himal"},
            headers={"hx-request": "true"},
        )
        body = response.content.decode()
        self.assertIn("Himal Cement", body)
        self.assertNotIn("<html", body)

    def test_creating_and_editing_an_item(self):
        self.client.post(
            reverse("chalani:item_create"),
            {
                "name": "Cement OPC 50kg",
                "name_np": "सिमेन्ट",
                "unit": "bag",
                "default_rate": "870",
                "is_active": "on",
            },
        )
        item = Item.objects.get(name="Cement OPC 50kg")
        self.assertEqual(item.organization, self.org)
        self.assertEqual(item.unit, "bag")

        self.client.post(
            reverse("chalani:item_edit", args=[item.pk]),
            {
                "name": "Cement OPC 50kg",
                "name_np": "",
                "unit": "kg",
                "default_rate": "",
                "is_active": "on",
            },
        )
        item.refresh_from_db()
        self.assertEqual(item.unit, "kg")
        self.assertIsNone(item.default_rate)

    def test_the_unit_dropdown_only_offers_canonical_codes(self):
        """Folding happens when a slip is read; the form itself takes codes."""
        response = self.client.post(
            reverse("chalani:item_create"),
            {"name": "Free text unit", "unit": "बोरा", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Item.objects.filter(name="Free text unit").exists())

    def test_another_firms_item_cannot_be_opened(self):
        foreign_item = Item.objects.create(organization=self.other, name="Rebar")
        self.assertEqual(
            self.client.get(
                reverse("chalani:item_edit", args=[foreign_item.pk])
            ).status_code,
            404,
        )


class TransitionTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.staff = make_org("Staff holder", "staff_user")[1]
        self.staff.memberships.all().delete()
        Membership.objects.create(
            organization=self.org, user=self.staff, role=Membership.Role.STAFF
        )
        self.staff.active_organization = self.org
        self.staff.save()

        self.vendor = Vendor.objects.create(organization=self.org, name="Himal Cement")
        self.item = Item.objects.create(
            organization=self.org, name="Cement", unit="bag"
        )
        self.chalani = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            vendor=self.vendor,
            chalani_no="C/1",
            date_bs="2082-05-17",
        )
        ChalaniItem.objects.create(
            chalani=self.chalani, item=self.item, description="सिमेन्ट", qty=10, rate=870
        )
        self.client.force_login(self.user)

    def verify(self):
        self.client.post(reverse("chalani:verify", args=[self.chalani.pk]))
        self.chalani.refresh_from_db()

    def test_billing_only_follows_verification(self):
        self.client.post(reverse("chalani:bill", args=[self.chalani.pk]))
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.status, Chalani.Status.DRAFT)

        self.verify()
        self.client.post(reverse("chalani:bill", args=[self.chalani.pk]))
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.status, Chalani.Status.BILLED)

    def test_reopening_clears_who_verified_it(self):
        self.verify()
        self.assertEqual(self.chalani.verified_by, self.user)
        self.client.post(reverse("chalani:reopen", args=[self.chalani.pk]))
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.status, Chalani.Status.DRAFT)
        self.assertIsNone(self.chalani.verified_by)
        self.assertIsNone(self.chalani.verified_at)

    def test_staff_may_not_bill_or_reopen(self):
        self.verify()
        self.client.force_login(self.staff)
        for name in ("bill", "reopen"):
            response = self.client.post(
                reverse(f"chalani:{name}", args=[self.chalani.pk])
            )
            self.assertEqual(response.status_code, 403, name)

    def test_a_billed_chalani_cannot_be_edited(self):
        self.verify()
        self.client.post(reverse("chalani:bill", args=[self.chalani.pk]))
        response = self.client.post(
            self.chalani.get_absolute_url(), {"chalani_no": "CHANGED"}, follow=True
        )
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.chalani_no, "C/1")
        self.assertTrue(
            any("billed" in m.lower() or "बिल" in m for m in messages_in(response))
        )

    def test_a_draft_can_be_deleted(self):
        response = self.client.post(reverse("chalani:delete", args=[self.chalani.pk]))
        self.assertRedirects(response, reverse("chalani:register"))
        self.assertFalse(Chalani.objects.filter(pk=self.chalani.pk).exists())

    def test_a_verified_chalani_cannot_be_deleted(self):
        self.verify()
        self.client.post(reverse("chalani:delete", args=[self.chalani.pk]))
        self.assertTrue(Chalani.objects.filter(pk=self.chalani.pk).exists())

    def test_another_firm_cannot_delete_a_draft(self):
        other, other_user = make_org("Other", "clerk_other")
        self.client.force_login(other_user)
        response = self.client.post(reverse("chalani:delete", args=[self.chalani.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Chalani.objects.filter(pk=self.chalani.pk).exists())

    def test_transitions_are_never_a_get(self):
        for name in ("verify", "bill", "reopen", "delete", "reextract"):
            response = self.client.get(
                reverse(f"chalani:{name}", args=[self.chalani.pk])
            )
            self.assertEqual(response.status_code, 405, name)


class ReextractTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.client.force_login(self.user)

    def _chalani(self, with_photo=True):
        kwargs = {}
        if with_photo:
            kwargs["photo"] = SimpleUploadedFile(
                "slip.png", PNG, content_type="image/png"
            )
        return Chalani.objects.create(
            organization=self.org, created_by=self.user, **kwargs
        )

    def test_a_chalani_with_no_photo_cannot_be_read_again(self):
        chalani = self._chalani(with_photo=False)
        with mock.patch("chalani.views.enqueue_extraction") as enqueue:
            self.client.post(reverse("chalani:reextract", args=[chalani.pk]))
        enqueue.assert_not_called()

    def test_ai_never_runs_over_lines_a_clerk_already_typed(self):
        chalani = self._chalani()
        ChalaniItem.objects.create(chalani=chalani, description="typed", qty=1)
        with mock.patch("chalani.views.enqueue_extraction") as enqueue:
            self.client.post(reverse("chalani:reextract", args=[chalani.pk]))
        enqueue.assert_not_called()

    def test_an_empty_draft_with_a_photo_is_queued_again(self):
        chalani = self._chalani()
        with mock.patch("chalani.views.enqueue_extraction") as enqueue:
            self.client.post(reverse("chalani:reextract", args=[chalani.pk]))
        enqueue.assert_called_once()


class StatusFragmentTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.chalani = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            status=Chalani.Status.EXTRACTING,
        )
        self.client.force_login(self.user)
        self.url = reverse("chalani:status", args=[self.chalani.pk])

    def test_while_reading_it_just_reports_the_status(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Refresh", response)

    def test_once_the_reading_lands_it_asks_htmx_to_reload(self):
        Chalani.objects.filter(pk=self.chalani.pk).update(status=Chalani.Status.DRAFT)
        response = self.client.get(self.url)
        self.assertEqual(response["HX-Refresh"], "true")

    def test_another_firm_cannot_poll_it(self):
        other, other_user = make_org("Other", "clerk_other")
        self.client.force_login(other_user)
        self.assertEqual(self.client.get(self.url).status_code, 404)


class PhotoTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.chalani = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            photo=SimpleUploadedFile("slip.png", PNG, content_type="image/png"),
        )
        self.client.force_login(self.user)
        self.url = reverse("chalani:photo", args=[self.chalani.pk])

    def test_it_is_served_with_its_own_content_type(self):
        response = self.client.get(self.url)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(b"".join(response.streaming_content), PNG)

    def test_it_is_never_cached_by_a_shared_proxy(self):
        response = self.client.get(self.url)
        self.assertIn("private", response["Cache-Control"])

    def test_it_opens_in_the_browser_rather_than_downloading_a_name(self):
        response = self.client.get(self.url)
        self.assertIn("inline", response["Content-Disposition"])
        self.assertNotIn("slip.png", response["Content-Disposition"])

    def test_a_chalani_without_a_photo_is_a_404_not_a_crash(self):
        bare = Chalani.objects.create(organization=self.org, created_by=self.user)
        response = self.client.get(reverse("chalani:photo", args=[bare.pk]))
        self.assertEqual(response.status_code, 404)

    def test_it_is_read_only(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_an_anonymous_visitor_gets_nothing(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])


class AddRowTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.chalani = Chalani.objects.create(
            organization=self.org, created_by=self.user
        )
        ChalaniItem.objects.create(chalani=self.chalani, description="सिमेन्ट", qty=1)
        self.client.force_login(self.user)
        self.url = reverse("chalani:add_row", args=[self.chalani.pk])

    def test_a_nonsense_total_falls_back_to_what_is_stored(self):
        response = self.client.get(self.url, {"items-TOTAL_FORMS": "many"})
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="items-1-description"', response.content.decode())

    def test_with_no_hint_it_counts_the_existing_lines(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn('name="items-1-description"', body)

    def test_the_new_row_only_offers_this_firms_catalog(self):
        Item.objects.create(organization=self.org, name="Cement")
        other, _user = make_org("Other", "clerk_other")
        Item.objects.create(organization=other, name="Foreign Rebar")
        body = self.client.get(self.url).content.decode()
        self.assertIn("Cement", body)
        self.assertNotIn("Foreign Rebar", body)


class UploadScreenTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.client.force_login(self.user)
        self.url = reverse("chalani:upload")

    def test_the_upload_form_is_shown(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="file"')

    def test_a_post_with_no_photo_re_renders_the_form(self):
        response = self.client.post(self.url, {"use_ai": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Chalani.objects.exists())

    def test_a_file_that_is_not_an_image_is_refused(self):
        response = self.client.post(
            self.url,
            {"photo": SimpleUploadedFile("notes.txt", b"not a photo", "text/plain")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Chalani.objects.exists())


class DetailFormTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.vendor = Vendor.objects.create(organization=self.org, name="Himal Cement")
        self.chalani = Chalani.objects.create(
            organization=self.org, created_by=self.user, vendor=self.vendor,
            chalani_no="C/1204", date_bs="2082-05-17",
        )
        self.line = ChalaniItem.objects.create(
            chalani=self.chalani, description="सिमेन्ट", qty=10, unit="bag", rate=870,
            line_no=1,
        )
        self.client.force_login(self.user)

    def payload(self, **overrides):
        data = {
            "vendor": self.vendor.pk,
            "chalani_no": "C/1204",
            "date_bs": "2082-05-17",
            "vehicle_no": "",
            "received_by": "",
            "remarks": "",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "1",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": self.line.pk,
            "items-0-chalani": self.chalani.pk,
            "items-0-description": "सिमेन्ट",
            "items-0-qty": "10",
            "items-0-unit": "bag",
            "items-0-rate": "870",
        }
        data.update(overrides)
        return data

    def test_a_bad_date_keeps_the_page_open_and_changes_nothing(self):
        response = self.client.post(
            self.chalani.get_absolute_url(), self.payload(date_bs="2082-99-99")
        )
        self.assertEqual(response.status_code, 200)
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.date_bs, "2082-05-17")

    def test_a_new_row_is_saved_and_numbered_after_the_existing_ones(self):
        data = self.payload(**{
            "items-TOTAL_FORMS": "2",
            "items-1-id": "",
            "items-1-chalani": self.chalani.pk,
            "items-1-description": "बाँध्ने तार",
            "items-1-qty": "१५.५",
            "items-1-unit": "kg",
            "items-1-rate": "142",
        })
        response = self.client.post(self.chalani.get_absolute_url(), data)
        self.assertEqual(response.status_code, 302)
        added = self.chalani.items.get(description="बाँध्ने तार")
        self.assertEqual(added.line_no, 2)
        self.assertEqual(str(added.qty), "15.500")

    def test_a_row_can_be_deleted(self):
        data = self.payload(**{"items-0-DELETE": "on"})
        self.client.post(self.chalani.get_absolute_url(), data)
        self.assertEqual(self.chalani.items.count(), 0)

    def test_the_supplier_dropdown_only_offers_this_firms_suppliers(self):
        other, _user = make_org("Other", "clerk_other")
        Vendor.objects.create(organization=other, name="Foreign Supplier")
        response = self.client.get(self.chalani.get_absolute_url())
        self.assertContains(response, "Himal Cement")
        self.assertNotContains(response, "Foreign Supplier")


class CatalogRedirectTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.client.force_login(self.user)

    def test_a_supplier_added_from_the_register_returns_to_the_register(self):
        response = self.client.post(
            reverse("chalani:vendor_create") + "?next=chalani",
            {"name": "Nepal Bitumen", "is_active": "on"},
        )
        self.assertRedirects(response, reverse("chalani:register"))

    def test_an_invalid_item_keeps_the_form_open(self):
        response = self.client.post(reverse("chalani:item_create"), {"name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Item.objects.exists())

    def test_the_item_list_answers_htmx_with_rows_only(self):
        Item.objects.create(organization=self.org, name="Cement")
        response = self.client.get(
            reverse("chalani:item_list"), {"q": "Cement"}, headers={"hx-request": "true"}
        )
        body = response.content.decode()
        self.assertIn("Cement", body)
        self.assertNotIn("<html", body)

    def test_a_supplier_links_to_its_own_edit_page(self):
        vendor = Vendor.objects.create(organization=self.org, name="Himal Cement")
        self.assertEqual(
            vendor.get_absolute_url(), reverse("chalani:vendor_edit", args=[vendor.pk])
        )
        self.assertEqual(self.client.get(vendor.get_absolute_url()).status_code, 200)


class CatalogFormPagesTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.item = Item.objects.create(organization=self.org, name="Cement", unit="bag")
        self.client.force_login(self.user)

    def test_the_item_list_renders_as_a_whole_page(self):
        response = self.client.get(reverse("chalani:item_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cement")
        self.assertContains(response, "<html")

    def test_the_new_item_form_renders(self):
        self.assertEqual(self.client.get(reverse("chalani:item_create")).status_code, 200)

    def test_the_edit_form_arrives_filled_in(self):
        response = self.client.get(reverse("chalani:item_edit", args=[self.item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Cement"')

    def test_the_new_supplier_form_renders(self):
        self.assertEqual(
            self.client.get(reverse("chalani:vendor_create")).status_code, 200
        )
