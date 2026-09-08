"""The MCP surface beyond scoping: every read tool, every write guard.

The web app and the server answer to the same rules, so these are the same
questions asked through the other door.
"""

import asyncio
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import TestCase, TransactionTestCase

from chalani import mcp_server as mcp
from chalani.models import Chalani, ChalaniItem, Item, Vendor
from chalani.tests import PNG, make_org
from nepal import dates as npdates


def today_bs_iso():
    today = npdates.today_bs()
    return f"{today.year}-{today.month:02d}-{today.day:02d}"


def seed_two_firms(case):
    """One firm with a full chalani, and a second firm that must stay invisible."""
    case.org, case.user = make_org("Nirman Sewa", "clerk_a")
    case.other, case.other_user = make_org("Other Firm", "clerk_b")

    case.vendor = Vendor.objects.create(
        organization=case.org, name="Himal Cement",
        name_np="हिमाल सिमेन्ट उद्योग", pan_no="600238914", district="काठमाडौँ",
    )
    case.item = Item.objects.create(
        organization=case.org, name="Cement OPC 50kg", unit="bag", default_rate=870
    )
    case.chalani = Chalani.objects.create(
        organization=case.org, created_by=case.user, vendor=case.vendor,
        chalani_no="C/1204", date_bs=today_bs_iso(), vehicle_no="बा १२ ख ३४५६",
        received_by="रमेश", photo=SimpleUploadedFile("s.png", PNG, "image/png"),
    )
    case.line = ChalaniItem.objects.create(
        chalani=case.chalani, description="सिमेन्ट", qty=10, unit="bag", rate=870
    )

    case.foreign_vendor = Vendor.objects.create(
        organization=case.other, name="Everest Steel", pan_no="123456789"
    )
    case.foreign_item = Item.objects.create(organization=case.other, name="Rebar")
    case.foreign_chalani = Chalani.objects.create(
        organization=case.other, created_by=case.other_user,
        vendor=case.foreign_vendor, chalani_no="SECRET/1", date_bs=today_bs_iso(),
    )


class RegisterFixture(TestCase):
    def setUp(self):
        seed_two_firms(self)


class SearchToolTests(RegisterFixture):
    def test_suppliers_are_found_in_either_script_or_by_pan(self):
        for needle in ("Himal", "हिमाल", "600238914", "६००२३८९१४"):
            found = mcp.search_vendors(self.org, query=needle)["vendors"]
            self.assertEqual([v["name"] for v in found], ["Himal Cement"], needle)

    def test_a_supplier_row_carries_its_chalani_count(self):
        found = mcp.search_vendors(self.org)["vendors"][0]
        self.assertEqual(found["chalani_count"], 1)
        self.assertEqual(found["district"], "काठमाडौँ")

    def test_supplier_search_never_crosses_firms(self):
        self.assertEqual(mcp.search_vendors(self.org, query="Everest")["vendors"], [])
        self.assertEqual(
            [v["name"] for v in mcp.search_vendors(self.other)["vendors"]],
            ["Everest Steel"],
        )

    def test_items_are_found_and_reported_with_a_readable_unit(self):
        found = mcp.search_items(self.org, query="Cement")["items"][0]
        self.assertEqual(found["unit"], "bag")
        self.assertEqual(found["unit_label"], "Bag / Sack")
        self.assertEqual(found["default_rate"], 870.0)

    def test_item_search_never_crosses_firms(self):
        self.assertEqual(mcp.search_items(self.org, query="Rebar")["items"], [])

    def test_a_search_with_no_query_lists_everything_that_firm_has(self):
        self.assertEqual(len(mcp.search_items(self.org)["items"]), 1)

    def test_the_limit_is_clamped_to_something_sane(self):
        for extra in range(5):
            Vendor.objects.create(organization=self.org, name=f"Vendor {extra}")
        self.assertEqual(len(mcp.search_vendors(self.org, limit=0)["vendors"]), 1)
        self.assertEqual(len(mcp.search_vendors(self.org, limit=2)["vendors"]), 2)
        self.assertEqual(len(mcp.search_vendors(self.org, limit=9999)["vendors"]), 6)


class ListAndGetTests(RegisterFixture):
    def test_a_row_carries_both_calendars_and_the_running_total(self):
        row = mcp.list_chalani(self.org)["chalani"][0]
        self.assertEqual(row["chalani_no"], "C/1204")
        self.assertEqual(row["vendor"], "हिमाल सिमेन्ट उद्योग")
        self.assertEqual(row["date_bs"], today_bs_iso())
        self.assertEqual(row["date_ad"], npdates.today_bs().to_datetime_date().isoformat())
        self.assertEqual(row["total"], 8700.0)

    def test_free_text_search_matches_the_same_things_the_register_does(self):
        for needle in ("C/1204", "बा १२ ख", "रमेश", "हिमाल", "सिमेन्ट"):
            self.assertEqual(mcp.list_chalani(self.org, query=needle)["count"], 1, needle)
        self.assertEqual(mcp.list_chalani(self.org, query="zzzz")["count"], 0)

    def test_filters_by_status_and_supplier(self):
        self.assertEqual(mcp.list_chalani(self.org, status="draft")["count"], 1)
        self.assertEqual(mcp.list_chalani(self.org, status="billed")["count"], 0)
        self.assertEqual(
            mcp.list_chalani(self.org, vendor_id=self.vendor.pk)["count"], 1
        )
        self.assertEqual(
            mcp.list_chalani(self.org, vendor_id=self.foreign_vendor.pk)["count"], 0
        )

    def test_a_bs_date_range_is_inclusive_at_both_ends(self):
        today = today_bs_iso()
        self.assertEqual(
            mcp.list_chalani(self.org, date_from_bs=today, date_to_bs=today)["count"], 1
        )

    def test_an_unreadable_date_argument_is_refused_rather_than_ignored(self):
        with self.assertRaises(npdates.InvalidBikramSambatDate):
            mcp.list_chalani(self.org, date_from_bs="2082-99-99")

    def test_the_limit_is_clamped(self):
        for n in range(3):
            Chalani.objects.create(
                organization=self.org, created_by=self.user, chalani_no=f"C/{n}"
            )
        self.assertEqual(mcp.list_chalani(self.org, limit=0)["count"], 1)
        self.assertEqual(mcp.list_chalani(self.org, limit=2)["count"], 2)
        self.assertEqual(mcp.list_chalani(self.org, limit=10_000)["count"], 4)

    def test_a_detail_carries_the_lines_and_what_still_blocks_verification(self):
        detail = mcp.get_chalani(self.org, self.chalani.pk)
        self.assertTrue(detail["has_photo"])
        self.assertEqual(detail["created_by"], self.user.display_name)
        self.assertIsNone(detail["verified_by"])
        self.assertEqual(detail["extraction_error"], "")
        line = detail["items"][0]
        self.assertEqual(line["line_id"], self.line.pk)
        self.assertEqual(line["qty"], 10.0)
        self.assertEqual(line["unit_label"], "Bag / Sack")
        self.assertEqual(line["amount"], 8700.0)
        self.assertIsNone(line["item"])
        self.assertTrue(detail["blocks_verification"])

    def test_a_verified_chalani_reports_who_signed_it_off(self):
        mcp.link_line_item(self.org, self.line.pk, self.item.pk)
        mcp.verify_chalani(self.org, self.chalani.pk, verified_by=self.user.username)
        detail = mcp.get_chalani(self.org, self.chalani.pk)
        self.assertEqual(detail["verified_by"], self.user.display_name)
        self.assertIsNotNone(detail["verified_at"])
        self.assertEqual(detail["blocks_verification"], [])


class SummaryTests(RegisterFixture):
    def test_the_summary_counts_this_firms_current_year(self):
        summary = mcp.register_summary(self.org)
        self.assertEqual(summary["organization"], str(self.org))
        self.assertEqual(summary["fiscal_year"], npdates.fiscal_year(npdates.today_bs()))
        self.assertEqual(summary["today_bs"], npdates.format_bs(npdates.today_bs()))
        self.assertEqual(summary["total_chalani"], 1)
        self.assertEqual(summary["counts"]["draft"], 1)
        self.assertEqual(summary["counts"]["billed"], 0)
        self.assertEqual(summary["total_amount"], 8700.0)
        self.assertEqual(summary["vendors"], 1)
        self.assertEqual(summary["items"], 1)

    def test_a_firm_with_nothing_in_it_still_answers(self):
        empty, _user = make_org("Empty", "clerk_empty")
        summary = mcp.register_summary(empty)
        self.assertEqual(summary["total_chalani"], 0)
        self.assertIsNone(summary["total_amount"])

    def test_pending_verification_lists_only_what_is_still_open(self):
        pending = mcp.pending_verification(self.org)
        self.assertEqual(pending["count"], 1)
        self.assertTrue(pending["chalani"][0]["blocks_verification"])

    def test_a_settled_chalani_drops_off_the_pending_list(self):
        mcp.link_line_item(self.org, self.line.pk, self.item.pk)
        mcp.verify_chalani(self.org, self.chalani.pk)
        self.assertEqual(mcp.pending_verification(self.org)["count"], 0)

    def test_pending_verification_never_crosses_firms(self):
        self.assertEqual(
            [c["chalani_no"] for c in mcp.pending_verification(self.other)["chalani"]],
            ["SECRET/1"],
        )


class ConvertDateTests(TestCase):
    def test_both_directions(self):
        self.assertEqual(mcp.convert_date(bs="2082-05-17")["ad"], "2025-09-02")
        self.assertEqual(mcp.convert_date(ad="2025-09-02")["bs"], "2082-05-17")

    def test_it_answers_with_the_weekday_and_fiscal_year(self):
        answer = mcp.convert_date(bs="2082-05-17")
        self.assertEqual(answer["weekday"], "Mangalbar")
        self.assertEqual(answer["fiscal_year"], "2082/83")
        self.assertEqual(answer["bs_nepali"], "१७ भदौ २०८२")

    def test_devanagari_digits_are_accepted_either_way(self):
        self.assertEqual(mcp.convert_date(bs="२०८२।०५।१७")["ad"], "2025-09-02")
        self.assertEqual(mcp.convert_date(ad="२०२५-०९-०२")["bs"], "2082-05-17")

    def test_exactly_one_side_must_be_given(self):
        with self.assertRaises(ValueError):
            mcp.convert_date()
        with self.assertRaises(ValueError):
            mcp.convert_date(bs="2082-05-17", ad="2025-09-02")

    def test_an_impossible_date_is_refused(self):
        with self.assertRaises(npdates.InvalidBikramSambatDate):
            mcp.convert_date(bs="2082-13-45")


class WriteToolTests(RegisterFixture):
    def test_omitted_fields_are_left_exactly_as_they_were(self):
        mcp.update_chalani(self.org, self.chalani.pk, received_by="सुनिता")
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.received_by, "सुनिता")
        self.assertEqual(self.chalani.chalani_no, "C/1204")
        self.assertEqual(self.chalani.vehicle_no, "बा १२ ख ३४५६")

    def test_an_empty_string_is_treated_as_omitted_not_as_a_blanking(self):
        mcp.update_chalani(self.org, self.chalani.pk, chalani_no="")
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.chalani_no, "C/1204")

    def test_it_reports_which_fields_it_touched(self):
        result = mcp.update_chalani(
            self.org, self.chalani.pk, remarks="half load", vendor_id=self.vendor.pk
        )
        self.assertEqual(sorted(result["updated"]), ["remarks", "vendor"])

    def test_a_bad_date_is_refused_and_nothing_is_saved(self):
        with self.assertRaises(npdates.InvalidBikramSambatDate):
            mcp.update_chalani(self.org, self.chalani.pk, date_bs="2082-13-45")
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.date_bs, today_bs_iso())

    def test_a_supplier_from_another_firm_cannot_be_attached(self):
        with self.assertRaises(Vendor.DoesNotExist):
            mcp.update_chalani(
                self.org, self.chalani.pk, vendor_id=self.foreign_vendor.pk
            )

    def test_another_firms_chalani_cannot_be_updated(self):
        with self.assertRaises(Chalani.DoesNotExist):
            mcp.update_chalani(self.other, self.chalani.pk, remarks="hijacked")

    def test_a_billed_chalani_is_closed_to_edits(self):
        Chalani.objects.filter(pk=self.chalani.pk).update(status=Chalani.Status.BILLED)
        with self.assertRaises(ValueError):
            mcp.update_chalani(self.org, self.chalani.pk, remarks="too late")

    def test_linking_a_line_to_another_firms_item_is_refused(self):
        with self.assertRaises(Item.DoesNotExist):
            mcp.link_line_item(self.org, self.line.pk, self.foreign_item.pk)

    def test_another_firms_line_cannot_be_linked(self):
        with self.assertRaises(ChalaniItem.DoesNotExist):
            mcp.link_line_item(self.other, self.line.pk, self.foreign_item.pk)

    def test_verification_falls_back_to_whoever_created_the_chalani(self):
        mcp.link_line_item(self.org, self.line.pk, self.item.pk)
        mcp.verify_chalani(self.org, self.chalani.pk, verified_by="nobody-by-that-name")
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.verified_by, self.user)

    def test_another_firms_chalani_cannot_be_verified(self):
        with self.assertRaises(Chalani.DoesNotExist):
            mcp.verify_chalani(self.other, self.chalani.pk)


class ServerShapeTests(RegisterFixture):
    def tools(self, allow_writes=False):
        return asyncio.run(
            mcp.build_server(self.org, allow_writes=allow_writes).list_tools()
        )

    def test_the_read_only_surface_is_exactly_the_read_tools(self):
        names = {tool.name for tool in self.tools()}
        expected = {fn.__name__ for fn in mcp.READ_TOOLS} | {"convert_date"}
        self.assertEqual(names, expected)

    def test_enabling_writes_adds_exactly_the_write_tools(self):
        read_only = {tool.name for tool in self.tools()}
        writable = {tool.name for tool in self.tools(allow_writes=True)}
        self.assertEqual(
            writable - read_only, {fn.__name__ for fn in mcp.WRITE_TOOLS}
        )

    def test_no_tool_ever_takes_an_organization(self):
        for tool in self.tools(allow_writes=True):
            self.assertNotIn("organization", tool.input_schema.get("properties", {}))

    def test_every_tool_explains_itself(self):
        for tool in self.tools(allow_writes=True):
            self.assertTrue(tool.description, tool.name)

    def test_reads_are_marked_read_only_and_nothing_is_destructive(self):
        by_name = {tool.name: tool for tool in self.tools(allow_writes=True)}
        self.assertTrue(by_name["list_chalani"].annotations.read_only_hint)
        self.assertFalse(by_name["verify_chalani"].annotations.read_only_hint)
        for tool in by_name.values():
            if tool.annotations is not None:
                self.assertFalse(tool.annotations.destructive_hint, tool.name)

    def test_the_arguments_a_caller_may_pass_are_the_documented_ones(self):
        by_name = {tool.name: tool for tool in self.tools(allow_writes=True)}
        self.assertEqual(
            set(by_name["list_chalani"].input_schema["properties"]),
            {"status", "vendor_id", "fiscal_year", "date_from_bs", "date_to_bs",
             "query", "limit"},
        )
        self.assertEqual(
            set(by_name["convert_date"].input_schema["properties"]), {"bs", "ad"}
        )

    def test_the_server_tells_the_client_which_firm_it_is_serving(self):
        server = mcp.build_server(self.org)
        self.assertEqual(server.name, "chalaani")
        self.assertIn(str(self.org), server.instructions)
        self.assertIn("Bikram Sambat", server.instructions)


class McpCommandTests(RegisterFixture):
    def call(self, *args):
        out = StringIO()
        call_command("mcp", *args, stdout=out)
        return out.getvalue()

    def test_listing_the_firms_that_can_be_served(self):
        printed = self.call("--list-orgs")
        self.assertIn(self.org.slug, printed)
        self.assertIn(self.other.slug, printed)
        self.assertIn("1 members", printed)

    def test_listing_the_tools_shows_writes_as_disabled_by_default(self):
        printed = self.call("--list-tools", "--org", self.org.slug)
        self.assertIn("list_chalani", printed)
        self.assertIn("convert_date", printed)
        self.assertIn("verify_chalani", printed)
        self.assertIn("write (disabled)", printed)

    def test_asking_for_writes_shows_them_as_enabled(self):
        printed = self.call("--list-tools", "--org", self.org.slug, "--allow-writes")
        self.assertNotIn("(disabled)", printed)

    def test_an_unknown_slug_names_the_slugs_that_do_exist(self):
        with self.assertRaises(CommandError) as caught:
            self.call("--list-tools", "--org", "no-such-firm")
        self.assertIn(self.org.slug, str(caught.exception))

    def test_with_several_firms_the_operator_must_choose_one(self):
        with self.assertRaises(CommandError) as caught:
            self.call("--list-tools")
        self.assertIn("--org", str(caught.exception))

    def test_with_one_firm_no_choice_is_needed(self):
        Chalani.objects.filter(organization=self.other).delete()
        self.other.delete()
        self.assertIn("list_chalani", self.call("--list-tools"))

    def test_with_no_firms_at_all_it_says_to_seed_one(self):
        Chalani.objects.all().delete()
        from orgs.models import Organization

        Organization.objects.all().delete()
        with self.assertRaises(CommandError) as caught:
            self.call("--list-tools")
        self.assertIn("seed_demo", str(caught.exception))


class ThroughTheServerTests(TransactionTestCase):
    """Calling a tool the way a client does, not by importing the function.

    The server runs each tool on a worker thread with its own connection, so
    these commit rather than sitting inside the test's transaction.
    """

    def setUp(self):
        seed_two_firms(self)

    def call(self, name, arguments=None, allow_writes=False, organization=None):
        server = mcp.build_server(organization or self.org, allow_writes=allow_writes)
        return asyncio.run(server.call_tool(name, arguments or {}))

    def payload(self, *args, **kwargs):
        return self.call(*args, **kwargs).structured_content["result"]

    def test_a_read_tool_answers_with_this_firms_rows(self):
        answer = self.payload("list_chalani")
        self.assertEqual(answer["count"], 1)
        self.assertEqual(answer["chalani"][0]["chalani_no"], "C/1204")

    def test_the_bound_firm_is_the_one_the_operator_pinned(self):
        """No argument a caller can pass changes which firm is served."""
        answer = self.payload("list_chalani", organization=self.other)
        self.assertEqual([row["chalani_no"] for row in answer["chalani"]], ["SECRET/1"])

    def test_arguments_reach_the_tool(self):
        self.assertEqual(self.payload("list_chalani", {"query": "zzzz"})["count"], 0)

    def test_convert_date_answers_through_the_server_too(self):
        import json

        result = self.call("convert_date", {"bs": "2082-05-17"})
        self.assertEqual(json.loads(result.content[0].text)["ad"], "2025-09-02")

    def test_a_write_tool_is_not_even_present_while_writes_are_off(self):
        from mcp.server.mcpserver.exceptions import ToolError

        with self.assertRaises(ToolError) as caught:
            self.call("verify_chalani", {"chalani_id": self.chalani.pk})
        self.assertIn("Unknown tool", str(caught.exception))
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.status, Chalani.Status.DRAFT)

    def test_a_write_tool_works_once_the_operator_enables_writes(self):
        self.call(
            "link_line_item",
            {"line_id": self.line.pk, "item_id": self.item.pk},
            allow_writes=True,
        )
        answer = self.payload(
            "verify_chalani", {"chalani_id": self.chalani.pk}, allow_writes=True
        )
        self.assertTrue(answer["verified"])
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.status, Chalani.Status.VERIFIED)

    def test_asking_for_another_firms_chalani_is_an_error_not_a_leak(self):
        from mcp.server.mcpserver.exceptions import UnexpectedToolError

        with self.assertRaises(UnexpectedToolError) as caught:
            self.call("get_chalani", {"chalani_id": self.foreign_chalani.pk})
        self.assertNotIn("SECRET/1", str(caught.exception))


class ServeCommandTests(RegisterFixture):
    """`manage.py mcp` without --list-* actually starts a server."""

    def test_stdio_is_the_default_transport(self):
        from unittest import mock

        with mock.patch("chalani.management.commands.mcp.build_server") as build:
            call_command("mcp", "--org", self.org.slug, stdout=StringIO(), stderr=StringIO())
        build.assert_called_once()
        self.assertFalse(build.call_args.kwargs["allow_writes"])
        build.return_value.run.assert_called_once_with("stdio")

    def test_http_carries_the_host_and_port_through(self):
        from unittest import mock

        with mock.patch("chalani.management.commands.mcp.build_server") as build:
            call_command(
                "mcp", "--org", self.org.slug, "--transport", "streamable-http",
                "--port", "8931", stdout=StringIO(), stderr=StringIO(),
            )
        build.return_value.run.assert_called_once_with(
            "streamable-http", host="127.0.0.1", port=8931
        )

    def test_the_banner_goes_to_stderr_so_it_never_corrupts_the_protocol(self):
        from unittest import mock

        out, err = StringIO(), StringIO()
        with mock.patch("chalani.management.commands.mcp.build_server"):
            call_command("mcp", "--org", self.org.slug, stdout=out, stderr=err)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("read-only", err.getvalue())
        self.assertIn(str(self.org), err.getvalue())

    def test_enabling_writes_is_announced(self):
        from unittest import mock

        err = StringIO()
        with mock.patch("chalani.management.commands.mcp.build_server") as build:
            call_command(
                "mcp", "--org", self.org.slug, "--allow-writes",
                stdout=StringIO(), stderr=err,
            )
        self.assertTrue(build.call_args.kwargs["allow_writes"])
        self.assertIn("writes enabled", err.getvalue())
