"""The demo seed — the first thing anyone runs after cloning."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from chalani.models import Chalani, ChalaniItem, Item, Vendor
from nepal import dates as npdates
from orgs.models import Membership, Organization

SLUG = "demo-nirman-sewa"


class SeedDemoTests(TestCase):
    def seed(self, *args, **options):
        out = StringIO()
        call_command("seed_demo", *args, stdout=out, **options)
        return out.getvalue()

    def test_it_creates_one_firm_with_a_catalog_and_a_register(self):
        self.seed(chalani=6)
        org = Organization.objects.get(slug=SLUG)
        self.assertEqual(Vendor.objects.for_org(org).count(), 5)
        self.assertEqual(Item.objects.for_org(org).count(), 10)
        self.assertEqual(Chalani.objects.for_org(org).count(), 6)
        self.assertTrue(ChalaniItem.objects.exists())

    def test_the_demo_login_in_the_readme_actually_works(self):
        self.seed(chalani=2)
        user = get_user_model().objects.get(username="demo")
        self.assertTrue(user.check_password("demo12345"))
        self.assertEqual(user.active_organization.slug, SLUG)
        self.assertTrue(self.client.login(username="demo", password="demo12345"))

    def test_the_demo_user_owns_the_demo_firm(self):
        self.seed(chalani=1)
        membership = Membership.objects.get(user__username="demo")
        self.assertEqual(membership.role, Membership.Role.OWNER)
        self.assertTrue(membership.can_verify)

    def test_every_seeded_chalani_lands_in_the_current_fiscal_year(self):
        self.seed(chalani=12)
        this_fy = npdates.fiscal_year(npdates.today_bs())
        for chalani in Chalani.objects.all():
            self.assertIsNotNone(chalani.date, chalani.chalani_no)
            self.assertEqual(chalani.fiscal_year, this_fy, chalani.chalani_no)

    def test_the_seeded_data_is_the_shape_the_screens_expect(self):
        self.seed(chalani=8)
        org = Organization.objects.get(slug=SLUG)
        statuses = set(Chalani.objects.for_org(org).values_list("status", flat=True))
        self.assertTrue(statuses <= {"draft", "verified", "billed"})
        for line in ChalaniItem.objects.all():
            self.assertTrue(line.description)
            self.assertGreater(line.qty, 0)
            self.assertIn(line.unit, [code for code, *_ in __import__("nepal.units", fromlist=["UNITS"]).UNITS])

    def test_running_it_twice_does_not_double_the_register(self):
        self.seed(chalani=4)
        self.seed(chalani=4)
        self.assertEqual(Organization.objects.filter(slug=SLUG).count(), 1)
        self.assertEqual(get_user_model().objects.filter(username="demo").count(), 1)
        self.assertEqual(Vendor.objects.count(), 5)
        self.assertEqual(Chalani.objects.count(), 4)

    def test_reset_starts_the_demo_firm_over(self):
        self.seed(chalani=4)
        first = set(Chalani.objects.values_list("chalani_no", flat=True))
        self.seed("--reset", chalani=4)
        self.assertEqual(Organization.objects.filter(slug=SLUG).count(), 1)
        self.assertEqual(Chalani.objects.count(), 4)
        self.assertEqual(set(Chalani.objects.values_list("chalani_no", flat=True)), first)

    def test_it_prints_the_login_it_just_created(self):
        printed = self.seed(chalani=1)
        self.assertIn("demo / demo12345", printed)

    def test_the_seeded_register_renders(self):
        self.seed(chalani=5)
        self.client.login(username="demo", password="demo12345")
        for name in ("chalani:dashboard", "chalani:register", "chalani:vendor_report"):
            from django.urls import reverse

            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)

    def test_it_is_reproducible_so_screenshots_match(self):
        self.seed(chalani=6)
        first = sorted(Chalani.objects.values_list("chalani_no", "date_bs"))
        self.seed("--reset", chalani=6)
        self.assertEqual(sorted(Chalani.objects.values_list("chalani_no", "date_bs")), first)
