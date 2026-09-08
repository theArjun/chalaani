"""Reading a photo: the contract, the gate, and the always-usable landing."""

import base64
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from pydantic import ValidationError

from chalani.models import Chalani, Item, Vendor
from chalani.tests import PNG, make_org
from extraction import chain, tasks
from extraction.schema import ChalaniExtraction, ExtractedItem

ENABLED = override_settings(EXTRACTION_ENABLED=True, ANTHROPIC_API_KEY="test-key")


class SchemaTests(TestCase):
    def test_a_blank_reading_is_valid_because_a_smudged_slip_is_normal(self):
        extraction = ChalaniExtraction()
        self.assertIsNone(extraction.vendor_name)
        self.assertIsNone(extraction.chalani_no)
        self.assertEqual(extraction.items, [])
        self.assertEqual(extraction.unreadable_fields, [])

    def test_it_admits_how_well_it_read_the_paper(self):
        extraction = ChalaniExtraction()
        self.assertEqual(extraction.legibility, "fair")
        self.assertEqual(extraction.confidence, 0.5)

    def test_confidence_is_a_probability(self):
        ChalaniExtraction(confidence=0.0)
        ChalaniExtraction(confidence=1.0)
        for outside in (-0.1, 1.1):
            with self.assertRaises(ValidationError):
                ChalaniExtraction(confidence=outside)

    def test_legibility_is_one_of_three_words(self):
        for word in ("good", "fair", "poor"):
            self.assertEqual(ChalaniExtraction(legibility=word).legibility, word)
        with self.assertRaises(ValidationError):
            ChalaniExtraction(legibility="excellent")

    def test_a_goods_line_must_at_least_say_what_it_was(self):
        with self.assertRaises(ValidationError):
            ExtractedItem()
        line = ExtractedItem(description="सिमेन्ट")
        self.assertIsNone(line.qty)
        self.assertIsNone(line.unit)
        self.assertIsNone(line.rate)

    def test_a_reading_survives_a_round_trip_through_json(self):
        extraction = ChalaniExtraction(
            vendor_name="Himal Cement Udyog",
            date_bs="2082-05-17",
            items=[ExtractedItem(description="सिमेन्ट", qty=120, unit="बोरा", rate=870)],
        )
        restored = ChalaniExtraction.model_validate(extraction.model_dump(mode="json"))
        self.assertEqual(restored, extraction)

    def test_the_schema_the_model_is_handed_names_the_nepali_fields(self):
        schema = ChalaniExtraction.model_json_schema()
        for field in ("vendor_pan", "date_bs", "date_ad", "vehicle_no", "items"):
            self.assertIn(field, schema["properties"])
        self.assertIn(
            "Bikram Sambat", schema["properties"]["date_bs"]["description"]
        )


class BuildChainTests(TestCase):
    @override_settings(EXTRACTION_ENABLED=False, ANTHROPIC_API_KEY="test-key")
    def test_switching_it_off_is_reported_as_unavailable_not_as_a_crash(self):
        with self.assertRaises(chain.ExtractionUnavailable) as caught:
            chain.build_chain()
        self.assertIn("CHALAANI_EXTRACTION_ENABLED", str(caught.exception))

    @override_settings(EXTRACTION_ENABLED=True, ANTHROPIC_API_KEY="")
    def test_a_missing_key_says_which_key(self):
        with self.assertRaises(chain.ExtractionUnavailable) as caught:
            chain.build_chain()
        self.assertIn("ANTHROPIC_API_KEY", str(caught.exception))

    @ENABLED
    def test_the_pipeline_is_a_structured_output_call_on_the_configured_model(self):
        with mock.patch("langchain_anthropic.ChatAnthropic") as llm:
            chain.build_chain()
        kwargs = llm.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-opus-5")
        self.assertEqual(kwargs["api_key"], "test-key")
        llm.return_value.with_structured_output.assert_called_once()
        structured = llm.return_value.with_structured_output.call_args
        self.assertIs(structured.args[0], ChalaniExtraction)
        self.assertEqual(structured.kwargs["method"], "json_schema")


class ExtractFromImageTests(TestCase):
    @ENABLED
    def test_the_photo_is_sent_as_base64_with_its_own_mime_type(self):
        with mock.patch.object(chain, "build_chain") as build:
            chain.extract_from_image(PNG, "image/png")
        messages = build.return_value.invoke.call_args.args[0]
        image_block = messages[1].content[0]
        self.assertEqual(image_block["mime_type"], "image/png")
        self.assertEqual(base64.standard_b64decode(image_block["base64"]), PNG)

    @ENABLED
    def test_the_prompt_tells_the_model_what_today_is_in_both_calendars(self):
        from nepal import dates as npdates

        with mock.patch.object(chain, "build_chain") as build:
            chain.extract_from_image(PNG)
        messages = build.return_value.invoke.call_args.args[0]
        instruction = messages[1].content[1]["text"]
        today = npdates.today_bs()
        self.assertIn(f"{today.year}-{today.month:02d}-{today.day:02d}", instruction)
        self.assertIn(today.to_datetime_date().isoformat(), instruction)

    @ENABLED
    def test_the_system_prompt_is_about_nepali_slips(self):
        with mock.patch.object(chain, "build_chain") as build:
            chain.extract_from_image(PNG)
        system = build.return_value.invoke.call_args.args[0][0].content
        self.assertIn("चलानी", system)


class EnqueueTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.chalani = Chalani.objects.create(
            organization=self.org, created_by=self.user,
            photo=SimpleUploadedFile("slip.png", PNG, content_type="image/png"),
        )

    @ENABLED
    def test_a_queued_chalani_says_it_is_being_read(self):
        with mock.patch("django_q.tasks.async_task", return_value="task-1") as async_task:
            task_id = tasks.enqueue_extraction(self.chalani)
        self.assertEqual(task_id, "task-1")
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.status, Chalani.Status.EXTRACTING)
        self.assertEqual(async_task.call_args.args[0], "extraction.tasks.run_extraction")
        self.assertEqual(async_task.call_args.args[1], self.chalani.pk)

    @ENABLED
    def test_queueing_clears_the_error_from_a_previous_attempt(self):
        Chalani.objects.filter(pk=self.chalani.pk).update(extraction_error="API down")
        with mock.patch("django_q.tasks.async_task"):
            tasks.enqueue_extraction(self.chalani)
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.extraction_error, "")

    def test_a_chalani_with_no_photo_is_never_queued(self):
        bare = Chalani.objects.create(organization=self.org, created_by=self.user)
        with mock.patch("django_q.tasks.async_task") as async_task:
            self.assertIsNone(tasks.enqueue_extraction(bare))
        async_task.assert_not_called()

    @override_settings(EXTRACTION_ENABLED=False)
    def test_with_ai_switched_off_it_lands_on_a_draft_that_says_why(self):
        """Never park a chalani in `extracting` when nothing can ever read it."""
        with mock.patch("django_q.tasks.async_task") as async_task:
            self.assertIsNone(tasks.enqueue_extraction(self.chalani))
        async_task.assert_not_called()
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.status, Chalani.Status.DRAFT)
        self.assertIn("CHALAANI_EXTRACTION_ENABLED", self.chalani.extraction_error)

    @override_settings(EXTRACTION_ENABLED=True, ANTHROPIC_API_KEY="")
    def test_with_no_api_key_it_lands_on_a_draft_that_says_why(self):
        with mock.patch("django_q.tasks.async_task") as async_task:
            self.assertIsNone(tasks.enqueue_extraction(self.chalani))
        async_task.assert_not_called()
        self.chalani.refresh_from_db()
        self.assertEqual(self.chalani.status, Chalani.Status.DRAFT)
        self.assertIn("ANTHROPIC_API_KEY", self.chalani.extraction_error)


class RunExtractionTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.vendor = Vendor.objects.create(
            organization=self.org, name="Himal Cement Udyog", pan_no="600238914"
        )
        self.item = Item.objects.create(
            organization=self.org, name="Cement OPC 50kg", unit="bag"
        )
        self.chalani = Chalani.objects.create(
            organization=self.org, created_by=self.user,
            photo=SimpleUploadedFile("slip.png", PNG, content_type="image/png"),
            status=Chalani.Status.EXTRACTING,
        )

    def run_with(self, **patch):
        with mock.patch.object(chain, "extract_from_image", **patch):
            result = tasks.run_extraction(self.chalani.pk)
        self.chalani.refresh_from_db()
        return result

    def reading(self):
        return ChalaniExtraction(
            vendor_pan="600238914",
            chalani_no="C/1204",
            date_bs="2082-05-17",
            items=[ExtractedItem(description="Cement OPC 50kg", qty=120, unit="बोरा", rate=870)],
            confidence=0.9,
        )

    def test_a_good_reading_lands_on_a_filled_in_draft(self):
        self.assertEqual(self.run_with(return_value=self.reading()), "ok")
        self.assertEqual(self.chalani.status, Chalani.Status.DRAFT)
        self.assertTrue(self.chalani.extracted_by_ai)
        self.assertEqual(self.chalani.extraction_error, "")
        self.assertEqual(self.chalani.vendor, self.vendor)
        self.assertEqual(self.chalani.items.get().item, self.item)
        self.assertEqual(self.chalani.items.get().rate, Decimal("870.00"))

    def test_the_raw_reading_is_kept_for_audit(self):
        self.run_with(return_value=self.reading())
        self.assertIn("extracted_at", self.chalani.raw_extraction)
        self.assertEqual(self.chalani.raw_extraction["data"]["chalani_no"], "C/1204")
        self.assertEqual(self.chalani.raw_extraction["data"]["confidence"], 0.9)

    def test_the_photo_is_sent_with_the_mime_type_it_was_stored_as(self):
        with mock.patch.object(
            chain, "extract_from_image", return_value=ChalaniExtraction()
        ) as extract:
            tasks.run_extraction(self.chalani.pk)
        self.assertEqual(extract.call_args.args[0], PNG)
        self.assertEqual(extract.call_args.args[1], "image/png")

    def test_an_unavailable_reader_leaves_an_editable_draft(self):
        result = self.run_with(
            side_effect=chain.ExtractionUnavailable("no key configured")
        )
        self.assertEqual(result, "unavailable")
        self.assertEqual(self.chalani.status, Chalani.Status.DRAFT)
        self.assertIn("no key configured", self.chalani.extraction_error)
        self.assertFalse(self.chalani.extracted_by_ai)

    def test_any_other_failure_also_leaves_an_editable_draft(self):
        with self.assertLogs("extraction.tasks", level="ERROR"):
            result = self.run_with(side_effect=RuntimeError("API down"))
        self.assertEqual(result, "error")
        self.assertEqual(self.chalani.status, Chalani.Status.DRAFT)
        self.assertIn("RuntimeError: API down", self.chalani.extraction_error)

    def test_a_very_long_error_is_trimmed_rather_than_overflowing(self):
        with self.assertLogs("extraction.tasks", level="ERROR"):
            self.run_with(side_effect=RuntimeError("x" * 5000))
        self.assertEqual(len(self.chalani.extraction_error), 2000)

    def test_a_missing_photo_file_is_a_draft_too_not_a_500(self):
        self.chalani.photo.storage.delete(self.chalani.photo.name)
        with self.assertLogs("extraction.tasks", level="ERROR"):
            result = tasks.run_extraction(self.chalani.pk)
        self.chalani.refresh_from_db()
        self.assertEqual(result, "error")
        self.assertEqual(self.chalani.status, Chalani.Status.DRAFT)
        self.assertTrue(self.chalani.extraction_error)


class ExtractCommandTests(TestCase):
    def setUp(self):
        self.org, self.user = make_org()
        self.chalani = Chalani.objects.create(
            organization=self.org, created_by=self.user,
            photo=SimpleUploadedFile("slip.png", PNG, content_type="image/png"),
        )

    def test_an_unknown_chalani_is_a_clean_command_error(self):
        with self.assertRaises(CommandError):
            call_command("extract_chalani", 99999)

    def test_it_reads_one_chalani_without_a_worker(self):
        from io import StringIO

        out = StringIO()
        with mock.patch.object(
            chain,
            "extract_from_image",
            return_value=ChalaniExtraction(
                chalani_no="C/1204",
                items=[ExtractedItem(description="सिमेन्ट", qty=1)],
            ),
        ):
            call_command("extract_chalani", self.chalani.pk, stdout=out)
        printed = out.getvalue()
        self.assertIn("result: ok", printed)
        self.assertIn("C/1204", printed)

    def test_a_failure_is_reported_on_the_command_line(self):
        from io import StringIO

        out = StringIO()
        with mock.patch.object(chain, "extract_from_image", side_effect=RuntimeError("API down")):
            with self.assertLogs("extraction.tasks", level="ERROR"):
                call_command("extract_chalani", self.chalani.pk, stdout=out)
        self.assertIn("API down", out.getvalue())
