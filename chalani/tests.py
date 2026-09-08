from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from chalani.models import Chalani, ChalaniItem, Item, Vendor
from chalani.services import apply_extraction, match_vendor
from extraction.schema import ChalaniExtraction, ExtractedItem
from orgs.models import Membership, Organization

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00"
    b"\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r"
    b"\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def make_org(name="Firm", username="clerk", role=Membership.Role.OWNER):
    organization = Organization.objects.create(name=name)
    user = get_user_model().objects.create_user(
        username=username, password="pw12345678"
    )
    Membership.objects.create(organization=organization, user=user, role=role)
    user.active_organization = organization
    user.save()
    return organization, user


class DateSyncTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()

    def test_bs_date_drives_ad_and_fiscal_year(self):
        chalani = Chalani.objects.create(
            organization=self.org, created_by=self.user, date_bs="२०८२।०५।१७"
        )
        self.assertEqual(chalani.date_bs, "2082-05-17")
        self.assertEqual(str(chalani.date), "2025-09-02")
        self.assertEqual(chalani.fiscal_year, "2082/83")

    def test_ad_only_fills_the_bs_mirror(self):
        chalani = Chalani.objects.create(
            organization=self.org, created_by=self.user, date="2025-09-02"
        )
        self.assertEqual(chalani.date_bs, "2082-05-17")

    def test_unparseable_bs_is_left_for_a_human(self):
        chalani = Chalani.objects.create(
            organization=self.org, created_by=self.user, date_bs="2082-99-99"
        )
        self.assertEqual(chalani.date_bs, "2082-99-99")
        self.assertIsNone(chalani.date)


class ConstraintTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.vendor = Vendor.objects.create(organization=self.org, name="Himal Cement")

    def _make(self, status, no="C/1204"):
        return Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            vendor=self.vendor,
            chalani_no=no,
            status=status,
        )

    def test_drafts_may_share_a_misread_number(self):
        self._make(Chalani.Status.DRAFT)
        self._make(Chalani.Status.DRAFT)  # no IntegrityError

    def test_verified_numbers_are_unique_per_vendor(self):
        self._make(Chalani.Status.VERIFIED)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._make(Chalani.Status.BILLED)

    def test_blank_numbers_do_not_collide(self):
        self._make(Chalani.Status.VERIFIED, no="")
        self._make(Chalani.Status.VERIFIED, no="")  # no IntegrityError


class ExtractionApplyTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.vendor = Vendor.objects.create(
            organization=self.org,
            name="Himal Cement Udyog",
            name_np="हिमाल सिमेन्ट उद्योग",
            pan_no="600238914",
        )
        self.item = Item.objects.create(
            organization=self.org,
            name="Cement OPC 50kg",
            name_np="सिमेन्ट ओ.पि.सि. ५० के.जी.",
            unit="bag",
        )

    def test_matches_vendor_by_pan_even_when_the_name_is_off(self):
        self.assertEqual(
            match_vendor(self.org, name="Himaal Siment", pan="600238914"), self.vendor
        )

    def test_matches_vendor_by_devanagari_name(self):
        self.assertEqual(
            match_vendor(self.org, name_np="हिमाल सिमेन्ट उद्योग"), self.vendor
        )

    def test_does_not_match_an_unrelated_vendor(self):
        self.assertIsNone(match_vendor(self.org, name="Everest Steel Traders"))

    def test_apply_extraction_fills_a_draft(self):
        chalani = Chalani.objects.create(organization=self.org, created_by=self.user)
        extraction = ChalaniExtraction(
            vendor_name="Himal Cement Udyog",
            vendor_pan="600238914",
            chalani_no="C/1204",
            date_bs="२०८२-०५-१७",
            vehicle_no="बा १२ ख ३४५६",
            received_by="रमेश श्रेष्ठ",
            items=[
                ExtractedItem(
                    description="सिमेन्ट ओ.पि.सि. ५० के.जी.",
                    qty=120,
                    unit="बोरा",
                    rate=870,
                ),
                ExtractedItem(description="बाँध्ने तार", qty=15.5, unit="kg"),
            ],
        )
        apply_extraction(chalani, extraction)
        chalani.save()
        chalani.refresh_from_db()

        self.assertEqual(chalani.vendor, self.vendor)
        self.assertEqual(chalani.chalani_no, "C/1204")
        self.assertEqual(chalani.date_bs, "2082-05-17")
        self.assertEqual(str(chalani.date), "2025-09-02")
        lines = list(chalani.items.all())
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].unit, "bag")  # बोरा folded onto the catalog code
        self.assertEqual(lines[0].item, self.item)
        self.assertEqual(lines[0].amount, Decimal("104400.00"))
        self.assertIsNone(lines[1].item)  # unknown item stays unlinked for a human
        self.assertEqual(lines[1].qty, Decimal("15.500"))

    def test_apply_extraction_never_overwrites_clerk_input(self):
        chalani = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            chalani_no="TYPED",
            date_bs="2082-01-01",
        )
        apply_extraction(
            chalani, ChalaniExtraction(chalani_no="AI", date_bs="2082-05-17")
        )
        self.assertEqual(chalani.chalani_no, "TYPED")
        self.assertEqual(chalani.date_bs, "2082-01-01")


class TenancyTests(TestCase):
    def setUp(self):
        self.org_a, self.user_a = make_org("A", "clerk_a")
        self.org_b, self.user_b = make_org("B", "clerk_b")
        self.chalani = Chalani.objects.create(
            organization=self.org_a,
            created_by=self.user_a,
            photo=SimpleUploadedFile("slip.png", PNG, content_type="image/png"),
        )

    def test_other_org_cannot_open_a_chalani(self):
        self.client.force_login(self.user_b)
        self.assertEqual(
            self.client.get(self.chalani.get_absolute_url()).status_code, 404
        )

    def test_other_org_cannot_fetch_the_photo(self):
        self.client.force_login(self.user_b)
        url = reverse("chalani:photo", args=[self.chalani.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_owner_can_fetch_the_photo(self):
        self.client.force_login(self.user_a)
        url = reverse("chalani:photo", args=[self.chalani.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(reverse("chalani:register"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])


class RegisterViewTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.vendor = Vendor.objects.create(organization=self.org, name="Himal Cement")
        self.chalani = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            vendor=self.vendor,
            chalani_no="C/1204",
            date_bs="2082-05-17",
        )
        ChalaniItem.objects.create(
            chalani=self.chalani, description="सिमेन्ट", qty=10, unit="bag", rate=870
        )
        self.client.force_login(self.user)

    def test_full_page_renders(self):
        response = self.client.get(reverse("chalani:register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "C/1204")
        self.assertContains(response, "१७ भदौ २०८२")

    def test_htmx_request_returns_only_the_fragment(self):
        response = self.client.get(
            reverse("chalani:register"), headers={"hx-request": "true"}
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("register-results", body)
        self.assertNotIn("<html", body)

    def test_bs_date_filter(self):
        response = self.client.get(reverse("chalani:register"), {"from": "2082-06-01"})
        self.assertNotContains(response, "C/1204")
        response = self.client.get(reverse("chalani:register"), {"from": "2082-01-01"})
        self.assertContains(response, "C/1204")

    def test_add_row_returns_a_row_and_bumps_total_forms(self):
        url = reverse("chalani:add_row", args=[self.chalani.pk])
        response = self.client.get(
            url, {"items-TOTAL_FORMS": "1"}, headers={"hx-request": "true"}
        )
        body = response.content.decode()
        self.assertIn('name="items-1-description"', body)
        self.assertIn('hx-swap-oob="true"', body)
        self.assertIn('value="2"', body)

    def test_saving_the_verify_form_updates_lines(self):
        line = self.chalani.items.first()
        response = self.client.post(
            self.chalani.get_absolute_url(),
            {
                "vendor": self.vendor.pk,
                "chalani_no": "C/1204",
                "date_bs": "2082-05-18",
                "vehicle_no": "बा १२ ख ३४५६",
                "received_by": "रमेश",
                "remarks": "",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "1",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-id": line.pk,
                "items-0-chalani": self.chalani.pk,
                "items-0-description": "सिमेन्ट ओ.पि.सि.",
                "items-0-qty": "१२",
                "items-0-unit": "bag",
                "items-0-rate": "875",
            },
        )
        self.assertEqual(response.status_code, 302)
        line.refresh_from_db()
        self.assertEqual(line.qty, Decimal("12.000"))  # Devanagari digits accepted
        self.chalani.refresh_from_db()
        self.assertEqual(str(self.chalani.date), "2025-09-03")


class VerifyFlowTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.staff = get_user_model().objects.create_user(
            username="staff", password="pw12345678"
        )
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
            chalani=self.chalani,
            item=self.item,
            description="सिमेन्ट",
            qty=10,
            unit="bag",
            rate=870,
        )

    def test_manager_can_verify_a_complete_chalani(self):
        self.client.force_login(self.user)
        self.client.post(reverse("chalani:verify", args=[self.chalani.pk]))
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.status, Chalani.Status.VERIFIED)
        self.assertEqual(self.chalani.verified_by, self.user)

    def test_staff_may_not_verify(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("chalani:verify", args=[self.chalani.pk]))
        self.assertEqual(response.status_code, 403)

    def test_incomplete_chalani_is_refused(self):
        self.chalani.items.all().delete()
        self.client.force_login(self.user)
        self.client.post(reverse("chalani:verify", args=[self.chalani.pk]))
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.status, Chalani.Status.DRAFT)

    def test_duplicate_verified_number_is_reported_not_crashed(self):
        Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            vendor=self.vendor,
            chalani_no="C/1",
            status=Chalani.Status.VERIFIED,
            date_bs="2082-05-01",
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("chalani:verify", args=[self.chalani.pk]), follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.status, Chalani.Status.DRAFT)
        self.assertContains(response, "पहिले नै प्रमाणित")


@override_settings(Q_CLUSTER={"name": "test", "orm": "default", "sync": True})
class UploadTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.client.force_login(self.user)

    def test_upload_creates_a_chalani_and_queues_extraction(self):
        with mock.patch("chalani.views.enqueue_extraction") as enqueue:
            response = self.client.post(
                reverse("chalani:upload"),
                {
                    "photo": SimpleUploadedFile(
                        "slip.png", PNG, content_type="image/png"
                    ),
                    "use_ai": "on",
                },
            )
        self.assertEqual(response.status_code, 302)
        chalani = Chalani.objects.get()
        self.assertTrue(chalani.photo.name.startswith(f"chalani/{self.org.pk}/"))
        enqueue.assert_called_once()

    def test_opting_out_of_ai_skips_the_queue(self):
        with mock.patch("chalani.views.enqueue_extraction") as enqueue:
            self.client.post(
                reverse("chalani:upload"),
                {
                    "photo": SimpleUploadedFile(
                        "slip.png", PNG, content_type="image/png"
                    )
                },
            )
        enqueue.assert_not_called()

    def test_a_failed_reading_lands_on_an_editable_draft(self):
        chalani = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            photo=SimpleUploadedFile("slip.png", PNG, content_type="image/png"),
            status=Chalani.Status.EXTRACTING,
        )
        from extraction.tasks import run_extraction

        with (
            mock.patch(
                "extraction.chain.extract_from_image",
                side_effect=RuntimeError("API down"),
            ),
            self.assertLogs("extraction.tasks", level="ERROR"),
        ):
            run_extraction(chalani.pk)
        chalani.refresh_from_db()
        self.assertEqual(chalani.status, Chalani.Status.DRAFT)
        self.assertIn("API down", chalani.extraction_error)


class LanguageSwitchTests(TestCase):
    """Nepali by default, English on request — and BS dates in both."""

    def setUp(self):
        self.org, self.user = make_org()
        vendor = Vendor.objects.create(organization=self.org, name="Himal Cement")
        self.chalani = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            vendor=vendor,
            chalani_no="C/1204",
            date_bs="2082-05-17",
        )
        self.client.force_login(self.user)

    def test_default_language_is_nepali(self):
        response = self.client.get(reverse("chalani:register"))
        self.assertContains(response, "चलानी दर्ता")
        self.assertContains(response, "१७ भदौ २०८२")

    def test_english_ui_keeps_bikram_sambat_dates(self):
        response = self.client.get(
            reverse("chalani:register"), headers={"accept-language": "en"}
        )
        self.assertContains(response, "Chalani register")
        self.assertContains(response, "17 Bhadau 2082")  # BS, in Latin script
        self.assertNotContains(response, "१७ भदौ")

    def test_set_language_sticks_for_later_requests(self):
        self.client.post(
            reverse("set_language"),
            {"language": "en", "next": reverse("chalani:register")},
        )
        response = self.client.get(reverse("chalani:register"))
        self.assertContains(response, "Chalani register")
        self.client.post(
            reverse("set_language"),
            {"language": "ne", "next": reverse("chalani:register")},
        )
        self.assertContains(self.client.get(reverse("chalani:register")), "चलानी दर्ता")

    def test_relative_date_is_shown_next_to_the_bs_date(self):
        from nepal.dates import bs_to_ad

        recent = Chalani.objects.create(
            organization=self.org,
            created_by=self.user,
            chalani_no="C/1205",
        )
        recent.date = bs_to_ad("2082-05-17")
        response = self.client.get(
            reverse("chalani:register"), headers={"accept-language": "en"}
        )
        self.assertRegex(response.content.decode(), r"\d+ (day|month|year)s? ago")

    def test_language_switch_is_a_plain_form_not_a_hover_menu(self):
        """Regression: the switcher lived in a daisyUI dropdown that never opened.

        The control has to be submittable from the page as rendered — one form,
        one submit button per language, no focus or hover state in between.
        """
        response = self.client.get(reverse("chalani:register"))
        body = response.content.decode()
        self.assertIn(f'action="{reverse("set_language")}"', body)
        for code in ("ne", "en"):
            self.assertIn(f'name="language" value="{code}"', body)
        header = body[: body.index("</header>")]
        self.assertIn('name="language"', header)
        # Nothing in the header may depend on a dropdown opening.
        self.assertNotIn('tabindex="0" role="button"', body)


class McpServerTests(TestCase):
    """The MCP surface obeys the same org scoping and write gating as the web app."""

    def setUp(self):
        from chalani import mcp_server

        self.mcp = mcp_server
        self.org_a, self.user_a = make_org("A", "clerk_a")
        self.org_b, self.user_b = make_org("B", "clerk_b")
        self.vendor = Vendor.objects.create(
            organization=self.org_a, name="Himal Cement", name_np="हिमाल सिमेन्ट उद्योग"
        )
        self.item = Item.objects.create(
            organization=self.org_a, name="Cement", unit="bag"
        )
        self.chalani = Chalani.objects.create(
            organization=self.org_a,
            created_by=self.user_a,
            vendor=self.vendor,
            chalani_no="C/1204",
            date_bs="2082-05-17",
        )
        self.line = ChalaniItem.objects.create(
            chalani=self.chalani, description="सिमेन्ट", qty=10, unit="bag", rate=870
        )
        Chalani.objects.create(
            organization=self.org_b, created_by=self.user_b, chalani_no="OTHER/1"
        )

    def test_listing_never_crosses_organizations(self):
        rows = self.mcp.list_chalani(self.org_a)["chalani"]
        self.assertEqual([r["chalani_no"] for r in rows], ["C/1204"])
        self.assertEqual(self.mcp.list_chalani(self.org_b)["count"], 1)

    def test_get_chalani_is_scoped(self):
        detail = self.mcp.get_chalani(self.org_a, self.chalani.pk)
        self.assertEqual(detail["vendor"], "हिमाल सिमेन्ट उद्योग")
        self.assertEqual(detail["items"][0]["amount"], 8700.0)
        self.assertIn("क्याटलग", " ".join(detail["blocks_verification"]))
        with self.assertRaises(Chalani.DoesNotExist):
            self.mcp.get_chalani(self.org_b, self.chalani.pk)

    def test_bs_dates_are_reported_both_ways(self):
        row = self.mcp.list_chalani(self.org_a)["chalani"][0]
        self.assertEqual(row["date_bs"], "2082-05-17")
        self.assertEqual(row["date_ad"], "2025-09-02")
        self.assertEqual(row["fiscal_year"], "2082/83")

    def test_convert_date_both_directions(self):
        self.assertEqual(self.mcp.convert_date(bs="2082-05-17")["ad"], "2025-09-02")
        self.assertEqual(self.mcp.convert_date(ad="2025-09-02")["bs"], "2082-05-17")
        with self.assertRaises(ValueError):
            self.mcp.convert_date()

    def test_filtering_by_fiscal_year_and_bs_range(self):
        self.assertEqual(
            self.mcp.list_chalani(self.org_a, fiscal_year="2082/83")["count"], 1
        )
        self.assertEqual(
            self.mcp.list_chalani(self.org_a, fiscal_year="2081/82")["count"], 0
        )
        self.assertEqual(
            self.mcp.list_chalani(self.org_a, date_from_bs="2082-06-01")["count"], 0
        )

    def test_write_tools_are_absent_unless_enabled(self):
        import asyncio

        read_only = asyncio.run(self.mcp.build_server(self.org_a).list_tools())
        writable = asyncio.run(
            self.mcp.build_server(self.org_a, allow_writes=True).list_tools()
        )
        self.assertNotIn("verify_chalani", [t.name for t in read_only])
        self.assertIn("verify_chalani", [t.name for t in writable])
        # `organization` is bound at startup, never exposed as a tool argument.
        for tool in writable:
            self.assertNotIn("organization", tool.input_schema.get("properties", {}))

    def test_server_is_named_chalaani(self):
        self.assertEqual(self.mcp.build_server(self.org_a).name, "chalaani")

    def test_verify_refuses_while_something_is_missing(self):
        result = self.mcp.verify_chalani(self.org_a, self.chalani.pk)
        self.assertFalse(result["verified"])
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.status, Chalani.Status.DRAFT)

    def test_link_then_verify(self):
        self.mcp.link_line_item(self.org_a, self.line.pk, self.item.pk)
        result = self.mcp.verify_chalani(self.org_a, self.chalani.pk)
        self.assertTrue(result["verified"])
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.status, Chalani.Status.VERIFIED)

    def test_update_keeps_omitted_fields_and_rejects_a_bad_date(self):
        self.mcp.update_chalani(self.org_a, self.chalani.pk, vehicle_no="बा १२ ख ३४५६")
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.chalani_no, "C/1204")  # untouched
        self.assertEqual(self.chalani.vehicle_no, "बा १२ ख ३४५६")
        with self.assertRaises(Exception):
            self.mcp.update_chalani(self.org_a, self.chalani.pk, date_bs="2082-13-45")

    def test_report_totals_match_the_lines(self):
        report = self.mcp.vendor_report(self.org_a, fiscal_year="2082/83")
        self.assertEqual(report["by_vendor"][0]["amount"], 8700.0)
        # Ashad 2083 runs to 32 days — the fiscal year ends on the last of it.
        self.assertEqual(report["period_bs"], ["2082-04-01", "2083-03-32"])
