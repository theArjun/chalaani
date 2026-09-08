"""The two HTMX endpoints behind the Bikram Sambat date input."""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from nepal import dates


class DatePreviewTests(TestCase):
    def setUp(self):
        self.url = reverse("nepal:date_preview")
        self.user = get_user_model().objects.create_user(
            username="clerk", password="pw12345678"
        )

    def test_it_is_behind_the_login(self):
        response = self.client.get(self.url, {"date_bs": "2082-05-17"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_it_echoes_the_gregorian_date_and_fiscal_year(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url, {"date_bs": "2082-05-17"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2025-09-02")
        self.assertContains(response, "2082/83")

    def test_the_script_follows_the_language_but_the_calendar_does_not(self):
        self.client.force_login(self.user)
        nepali = self.client.get(self.url, {"date_bs": "2082-05-17"})
        self.assertContains(nepali, "१७ भदौ २०८२")
        self.assertContains(nepali, "मंगलबार")
        english = self.client.get(
            self.url, {"date_bs": "2082-05-17"}, headers={"accept-language": "en"}
        )
        self.assertContains(english, "17 Bhadau 2082")
        self.assertContains(english, "Mangalbar")
        self.assertNotContains(english, "१७ भदौ")

    def test_it_reads_whichever_query_parameter_carries_the_date(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url, {"items-3-date_bs": "2082-05-17"})
        self.assertContains(response, "2025-09-02")

    def test_devanagari_input_previews_too(self):
        self.client.force_login(self.user)
        self.assertContains(
            self.client.get(self.url, {"d": "२०८२।०५।१७"}), "2025-09-02"
        )

    def test_a_half_typed_date_reports_the_problem_instead_of_erroring(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url, {"date_bs": "2082-9"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "text-error")
        self.assertNotContains(response, "✓")

    def test_an_impossible_date_reports_the_problem(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url, {"date_bs": "2082-13-45"})
        self.assertContains(response, "text-error")

    def test_nothing_typed_yet_renders_nothing(self):
        self.client.force_login(self.user)
        for params in ({}, {"date_bs": ""}, {"date_bs": "   "}):
            response = self.client.get(self.url, params)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content.decode().strip(), "")

    def test_it_is_read_only(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.post(self.url, {"date_bs": "2082-05-17"}).status_code, 405
        )


class DateInputTests(TestCase):
    def setUp(self):
        self.url = reverse("nepal:date_input")
        self.user = get_user_model().objects.create_user(
            username="clerk", password="pw12345678"
        )
        self.client.force_login(self.user)

    def test_it_renders_a_named_input_wired_to_the_preview(self):
        response = self.client.get(self.url)
        body = response.content.decode()
        self.assertIn('name="date_bs"', body)
        self.assertIn('id="id_date_bs"', body)
        self.assertIn(reverse("nepal:date_preview"), body)

    def test_the_today_button_fills_in_the_current_bs_date(self):
        response = self.client.get(self.url, {"value": "today"})
        today = dates.today_bs()
        self.assertContains(
            response, f'value="{today.year}-{today.month:02d}-{today.day:02d}"'
        )
        self.assertEqual(today.to_datetime_date(), datetime.date.today())

    def test_a_formset_row_gets_its_own_name(self):
        response = self.client.get(
            self.url, {"name": "items-2-date_bs", "value": "2082-05-17"}
        )
        body = response.content.decode()
        self.assertIn('name="items-2-date_bs"', body)
        self.assertIn('value="2082-05-17"', body)

    def test_it_is_behind_the_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
