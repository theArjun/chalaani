"""Tenancy: slugs, roles, the current-organization middleware, and the screens.

Every one of these is really the same question — can a member of one firm reach
another firm's rows, or do something their role does not allow?
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse

from chalani.models import Vendor
from orgs.middleware import CurrentOrganizationMiddleware
from orgs.mixins import org_objects, org_required, verifier_required
from orgs.models import Membership, Organization


def make_user(username="clerk", **extra):
    return get_user_model().objects.create_user(
        username=username, password="pw12345678", **extra
    )


def join(organization, user, role=Membership.Role.OWNER):
    membership = Membership.objects.create(
        organization=organization, user=user, role=role
    )
    user.active_organization = organization
    user.save(update_fields=["active_organization"])
    return membership


class OrganizationModelTests(TestCase):
    def test_the_slug_comes_from_the_name(self):
        org = Organization.objects.create(name="Demo Nirman Sewa")
        self.assertEqual(org.slug, "demo-nirman-sewa")

    def test_a_second_firm_of_the_same_name_gets_its_own_slug(self):
        first = Organization.objects.create(name="Shree Ram Traders")
        second = Organization.objects.create(name="Shree Ram Traders")
        third = Organization.objects.create(name="Shree Ram Traders")
        self.assertEqual(
            [first.slug, second.slug],
            ["shree-ram-traders", "shree-ram-traders-2"],
        )
        self.assertEqual(third.slug, "shree-ram-traders-3")

    def test_a_devanagari_only_name_still_gets_a_usable_slug(self):
        org = Organization.objects.create(name="श्री राम ट्रेडर्स")
        self.assertTrue(org.slug)
        self.assertEqual(Organization.objects.get(slug=org.slug), org)

    def test_renaming_a_firm_keeps_its_slug_stable(self):
        org = Organization.objects.create(name="Old Name")
        org.name = "New Name"
        org.save()
        self.assertEqual(org.slug, "old-name")

    def test_an_explicit_slug_is_respected(self):
        org = Organization.objects.create(name="Anything", slug="chosen")
        self.assertEqual(org.slug, "chosen")

    def test_it_prints_the_nepali_name_when_there_is_one(self):
        org = Organization.objects.create(name="Himal Cement", name_np="हिमाल सिमेन्ट")
        self.assertEqual(str(org), "हिमाल सिमेन्ट")
        self.assertEqual(
            str(Organization.objects.create(name="Only English")), "Only English"
        )


class MembershipTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Firm")
        self.user = make_user()

    def test_a_user_joins_a_firm_only_once(self):
        Membership.objects.create(organization=self.org, user=self.user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(organization=self.org, user=self.user)

    def test_the_same_user_may_belong_to_several_firms(self):
        other = Organization.objects.create(name="Other")
        Membership.objects.create(organization=self.org, user=self.user)
        Membership.objects.create(organization=other, user=self.user)
        self.assertEqual(self.user.memberships.count(), 2)

    def test_only_owners_and_managers_verify(self):
        cases = {
            Membership.Role.OWNER: True,
            Membership.Role.MANAGER: True,
            Membership.Role.STAFF: False,
        }
        for role, expected in cases.items():
            membership = Membership(organization=self.org, user=self.user, role=role)
            self.assertEqual(membership.can_verify, expected, role)

    def test_new_members_start_as_staff(self):
        membership = Membership.objects.create(organization=self.org, user=self.user)
        self.assertEqual(membership.role, Membership.Role.STAFF)
        self.assertFalse(membership.can_verify)

    def test_removing_a_firm_removes_its_memberships_not_its_users(self):
        Membership.objects.create(organization=self.org, user=self.user)
        self.org.delete()
        self.assertFalse(Membership.objects.exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())


class OrgScopedQuerySetTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name="A")
        self.org_b = Organization.objects.create(name="B")
        Vendor.objects.create(organization=self.org_a, name="Himal Cement")
        Vendor.objects.create(organization=self.org_b, name="Everest Steel")

    def test_for_org_returns_only_that_firms_rows(self):
        self.assertEqual(
            [v.name for v in Vendor.objects.for_org(self.org_a)], ["Himal Cement"]
        )

    def test_no_organization_means_no_rows_rather_than_all_rows(self):
        self.assertEqual(Vendor.objects.for_org(None).count(), 0)


class MiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = CurrentOrganizationMiddleware(lambda request: "ok")

    def _run(self, user):
        request = self.factory.get("/")
        request.user = user
        self.middleware(request)
        return request

    def test_anonymous_requests_carry_no_organization(self):
        from django.contrib.auth.models import AnonymousUser

        request = self._run(AnonymousUser())
        self.assertIsNone(request.organization)
        self.assertIsNone(request.membership)

    def test_a_user_without_a_firm_carries_no_organization(self):
        request = self._run(make_user())
        self.assertIsNone(request.organization)

    def test_the_active_pointer_decides_which_firm_is_current(self):
        user = make_user()
        first = Organization.objects.create(name="A")
        second = Organization.objects.create(name="B")
        Membership.objects.create(organization=first, user=user)
        Membership.objects.create(organization=second, user=user)
        user.active_organization = second
        user.save(update_fields=["active_organization"])

        request = self._run(user)
        self.assertEqual(request.organization, second)
        self.assertEqual(request.membership.organization, second)

    def test_a_stale_pointer_is_healed_rather_than_left_broken(self):
        """The firm a user pointed at was deleted — fall back and remember."""
        user = make_user()
        gone = Organization.objects.create(name="Gone")
        kept = Organization.objects.create(name="Kept")
        Membership.objects.create(organization=kept, user=user)
        user.active_organization = gone
        user.save(update_fields=["active_organization"])
        gone.delete()

        request = self._run(user)
        self.assertEqual(request.organization, kept)
        user.refresh_from_db()
        self.assertEqual(user.active_organization, kept)

    def test_an_unset_pointer_is_filled_in_on_the_first_request(self):
        user = make_user()
        org = Organization.objects.create(name="Firm")
        Membership.objects.create(organization=org, user=user)
        self.assertIsNone(user.active_organization)

        self._run(user)
        user.refresh_from_db()
        self.assertEqual(user.active_organization, org)


class DecoratorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.org = Organization.objects.create(name="Firm")

    def _request(self, user, organization=None, membership=None):
        request = self.factory.get("/")
        request.user = user
        request.organization = organization
        request.membership = membership
        return request

    def test_org_required_sends_a_firmless_user_to_register_one(self):
        view = org_required(lambda request: "reached")
        response = view(self._request(make_user()))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("orgs:create"))

    def test_org_required_lets_a_member_through(self):
        user = make_user()
        membership = join(self.org, user)
        view = org_required(lambda request: "reached")
        self.assertEqual(view(self._request(user, self.org, membership)), "reached")

    def test_verifier_required_refuses_staff(self):
        user = make_user("staff")
        membership = join(self.org, user, Membership.Role.STAFF)
        view = verifier_required(lambda request: "reached")
        with self.assertRaises(PermissionDenied):
            view(self._request(user, self.org, membership))

    def test_verifier_required_admits_a_manager(self):
        user = make_user("manager")
        membership = join(self.org, user, Membership.Role.MANAGER)
        view = verifier_required(lambda request: "reached")
        self.assertEqual(view(self._request(user, self.org, membership)), "reached")

    def test_org_objects_is_scoped(self):
        other = Organization.objects.create(name="Other")
        Vendor.objects.create(organization=other, name="Everest Steel")
        request = self._request(make_user(), self.org)
        self.assertEqual(org_objects(Vendor, request).count(), 0)


class CreateFirmViewTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)

    def test_the_form_is_shown_to_a_firmless_user(self):
        response = self.client.get(reverse("orgs:create"))
        self.assertEqual(response.status_code, 200)

    def test_creating_a_firm_makes_the_creator_its_owner(self):
        response = self.client.post(
            reverse("orgs:create"),
            {
                "name": "Shree Ram Traders",
                "name_np": "श्री राम ट्रेडर्स",
                "pan_no": "600238914",
                "phone": "9812345678",
                "address": "",
                "district": "Kathmandu",
            },
        )
        self.assertRedirects(response, reverse("chalani:dashboard"))
        org = Organization.objects.get(name="Shree Ram Traders")
        membership = Membership.objects.get(organization=org, user=self.user)
        self.assertEqual(membership.role, Membership.Role.OWNER)
        self.user.refresh_from_db()
        self.assertEqual(self.user.active_organization, org)

    def test_a_bad_pan_is_reported_and_nothing_is_created(self):
        response = self.client.post(
            reverse("orgs:create"), {"name": "Firm", "pan_no": "123"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Organization.objects.exists())

    def test_anonymous_visitors_are_sent_to_the_login(self):
        self.client.logout()
        response = self.client.get(reverse("orgs:create"))
        self.assertIn("/accounts/login/", response["Location"])


class SwitchFirmTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.first = Organization.objects.create(name="A")
        self.second = Organization.objects.create(name="B")
        join(self.first, self.user)
        Membership.objects.create(organization=self.second, user=self.user)
        self.client.force_login(self.user)

    def test_switching_moves_the_pointer(self):
        response = self.client.post(reverse("orgs:switch", args=[self.second.pk]))
        self.assertRedirects(response, reverse("chalani:dashboard"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.active_organization, self.second)

    def test_a_firm_you_do_not_belong_to_is_not_switchable(self):
        outsider = Organization.objects.create(name="Someone else's firm")
        response = self.client.post(reverse("orgs:switch", args=[outsider.pk]))
        self.assertEqual(response.status_code, 404)
        self.user.refresh_from_db()
        self.assertEqual(self.user.active_organization, self.first)

    def test_switching_is_never_a_get(self):
        self.assertEqual(
            self.client.get(reverse("orgs:switch", args=[self.second.pk])).status_code,
            405,
        )


class SettingsViewTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Firm")
        self.owner = make_user("owner")
        join(self.org, self.owner)
        self.staff = make_user("staff")
        join(self.org, self.staff, Membership.Role.STAFF)
        self.outsider = make_user("outsider")
        self.url = reverse("orgs:settings")

    def test_a_firmless_user_is_sent_to_register_one(self):
        self.client.force_login(self.outsider)
        self.assertRedirects(self.client.get(self.url), reverse("orgs:create"))

    def test_the_owner_can_rename_the_firm(self):
        self.client.force_login(self.owner)
        self.client.post(
            self.url,
            {
                "name": "Renamed Firm",
                "name_np": "",
                "pan_no": "",
                "phone": "",
                "address": "",
                "district": "",
            },
        )
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "Renamed Firm")

    def test_staff_may_look_but_not_change(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.post(self.url, {"name": "Hijacked"})
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "Firm")

    def test_the_owner_can_add_an_existing_user(self):
        self.client.force_login(self.owner)
        self.client.post(
            self.url,
            {
                "add_member": "1",
                "username": "outsider",
                "role": Membership.Role.MANAGER,
            },
        )
        membership = Membership.objects.get(organization=self.org, user=self.outsider)
        self.assertEqual(membership.role, Membership.Role.MANAGER)

    def test_usernames_are_matched_case_insensitively(self):
        self.client.force_login(self.owner)
        self.client.post(
            self.url,
            {
                "add_member": "1",
                "username": " OUTSIDER ",
                "role": Membership.Role.STAFF,
            },
        )
        self.assertTrue(
            Membership.objects.filter(
                organization=self.org, user=self.outsider
            ).exists()
        )

    def test_adding_an_unknown_user_is_a_form_error(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            self.url,
            {"add_member": "1", "username": "nobody", "role": Membership.Role.STAFF},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.org.memberships.count(), 2)

    def test_adding_an_existing_member_does_not_change_their_role(self):
        self.client.force_login(self.owner)
        self.client.post(
            self.url,
            {"add_member": "1", "username": "staff", "role": Membership.Role.OWNER},
        )
        self.assertEqual(
            Membership.objects.get(organization=self.org, user=self.staff).role,
            Membership.Role.STAFF,
        )


class RemoveMemberTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Firm")
        self.owner = make_user("owner")
        join(self.org, self.owner)
        self.staff = make_user("staff")
        self.staff_membership = join(self.org, self.staff, Membership.Role.STAFF)

    def test_the_owner_can_remove_a_member(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("orgs:remove_member", args=[self.staff_membership.pk]))
        self.assertFalse(
            Membership.objects.filter(pk=self.staff_membership.pk).exists()
        )

    def test_staff_cannot_remove_anyone(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("orgs:remove_member", args=[self.staff_membership.pk]))
        self.assertTrue(Membership.objects.filter(pk=self.staff_membership.pk).exists())

    def test_an_owner_cannot_lock_themselves_out(self):
        own = Membership.objects.get(organization=self.org, user=self.owner)
        self.client.force_login(self.owner)
        self.client.post(reverse("orgs:remove_member", args=[own.pk]))
        self.assertTrue(Membership.objects.filter(pk=own.pk).exists())

    def test_a_membership_in_another_firm_is_not_reachable(self):
        other = Organization.objects.create(name="Other")
        stranger = make_user("stranger")
        foreign = Membership.objects.create(organization=other, user=stranger)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("orgs:remove_member", args=[foreign.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Membership.objects.filter(pk=foreign.pk).exists())


class ReadableNamesTests(TestCase):
    """Whatever the admin and the logs print has to name the firm and the role."""

    def test_a_membership_prints_who_belongs_where_and_as_what(self):
        org = Organization.objects.create(name="Himal Cement", name_np="हिमाल सिमेन्ट")
        user = make_user("ramesh")
        membership = Membership.objects.create(
            organization=org, user=user, role=Membership.Role.MANAGER
        )
        printed = str(membership)
        self.assertIn("ramesh", printed)
        self.assertIn("हिमाल सिमेन्ट", printed)
        self.assertIn("manager", printed)

    def test_memberships_are_listed_by_firm_name(self):
        user = make_user("ramesh")
        for name in ("Zebra Traders", "Apex Suppliers", "Mid Hardware"):
            Membership.objects.create(
                organization=Organization.objects.create(name=name), user=user
            )
        self.assertEqual(
            [m.organization.name for m in Membership.objects.all()],
            ["Apex Suppliers", "Mid Hardware", "Zebra Traders"],
        )
