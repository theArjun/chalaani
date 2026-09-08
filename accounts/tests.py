"""Signing up, logging in, and what a user is called on screen."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.forms import SignupForm
from orgs.models import Membership, Organization

User = get_user_model()

SIGNUP = {
    "username": "ramesh",
    "email": "ramesh@example.com",
    "password1": "chalaani-pw-12345",
    "password2": "chalaani-pw-12345",
    "full_name_np": "रमेश श्रेष्ठ",
    "phone": "9812345678",
    "organization_name": "Shree Ram Traders",
    "organization_name_np": "श्री राम ट्रेडर्स",
}


class UserModelTests(TestCase):
    def test_the_nepali_name_is_what_a_user_is_called(self):
        user = User.objects.create_user(
            username="ramesh", password="pw12345678",
            full_name_np="रमेश श्रेष्ठ", first_name="Ramesh", last_name="Shrestha",
        )
        self.assertEqual(str(user), "रमेश श्रेष्ठ")
        self.assertEqual(user.display_name, "रमेश श्रेष्ठ")

    def test_without_one_the_latin_name_is_used(self):
        user = User.objects.create_user(
            username="ramesh", password="pw12345678",
            first_name="Ramesh", last_name="Shrestha",
        )
        self.assertEqual(user.display_name, "Ramesh Shrestha")

    def test_with_no_name_at_all_the_username_stands_in(self):
        user = User.objects.create_user(username="ramesh", password="pw12345678")
        self.assertEqual(user.display_name, "ramesh")

    def test_a_users_phone_is_validated(self):
        user = User(username="ramesh", phone="12345")
        with self.assertRaises(ValidationError):
            user.full_clean()

    def test_a_new_user_belongs_to_no_firm_yet(self):
        user = User.objects.create_user(username="ramesh", password="pw12345678")
        self.assertIsNone(user.active_organization)
        self.assertEqual(user.memberships.count(), 0)

    def test_deleting_the_active_firm_leaves_the_user_standing(self):
        user = User.objects.create_user(username="ramesh", password="pw12345678")
        org = Organization.objects.create(name="Firm")
        user.active_organization = org
        user.save()
        org.delete()
        user.refresh_from_db()
        self.assertIsNone(user.active_organization)


class SignupFormTests(TestCase):
    def test_one_form_creates_the_user_the_firm_and_the_ownership(self):
        form = SignupForm(SIGNUP)
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertEqual(user.full_name_np, "रमेश श्रेष्ठ")
        self.assertEqual(user.phone, "9812345678")
        org = Organization.objects.get(name="Shree Ram Traders")
        self.assertEqual(org.name_np, "श्री राम ट्रेडर्स")
        self.assertEqual(user.active_organization, org)
        self.assertEqual(
            Membership.objects.get(organization=org, user=user).role,
            Membership.Role.OWNER,
        )

    def test_the_password_is_stored_hashed(self):
        user = SignupForm(SIGNUP).save() if SignupForm(SIGNUP).is_valid() else None
        self.assertIsNotNone(user)
        self.assertNotIn("chalaani-pw-12345", user.password)
        self.assertTrue(user.check_password("chalaani-pw-12345"))

    def test_a_nepali_firm_name_is_optional(self):
        form = SignupForm(SIGNUP | {"organization_name_np": ""})
        self.assertTrue(form.is_valid(), form.errors)

    def test_a_firm_name_is_not_optional(self):
        form = SignupForm(SIGNUP | {"organization_name": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("organization_name", form.errors)

    def test_mismatched_passwords_are_refused(self):
        form = SignupForm(SIGNUP | {"password2": "something-else-entirely"})
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_a_taken_username_is_refused(self):
        User.objects.create_user(username="ramesh", password="pw12345678")
        form = SignupForm(SIGNUP)
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)


class SignupViewTests(TestCase):
    def setUp(self):
        self.url = reverse("accounts:signup")

    def test_the_form_is_public(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_signing_up_logs_you_straight_in(self):
        response = self.client.post(self.url, SIGNUP)
        self.assertRedirects(response, reverse("chalani:dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), User.objects.get().pk)

    def test_a_rejected_form_creates_nothing(self):
        response = self.client.post(self.url, SIGNUP | {"password2": "mismatch"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())
        self.assertFalse(Organization.objects.exists())

    def test_someone_already_signed_in_is_sent_to_their_register(self):
        User.objects.create_user(username="ramesh", password="pw12345678")
        self.client.login(username="ramesh", password="pw12345678")
        self.assertRedirects(
            self.client.get(self.url),
            reverse("chalani:dashboard"),
            fetch_redirect_response=False,
        )


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ramesh", password="pw12345678")
        self.url = reverse("accounts:login")

    def test_the_login_page_renders(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_correct_credentials_get_in(self):
        response = self.client.post(
            self.url, {"username": "ramesh", "password": "pw12345678"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_a_wrong_password_does_not(self):
        response = self.client.post(
            self.url, {"username": "ramesh", "password": "wrong-password"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_someone_already_signed_in_is_not_shown_the_form_again(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_logging_out_ends_the_session(self):
        self.client.force_login(self.user)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logging_out_is_never_a_get(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_the_register_sends_a_stranger_to_the_login_and_back(self):
        response = self.client.get(reverse("chalani:register"))
        self.assertIn(reverse("accounts:login"), response["Location"])
        self.assertIn("next=", response["Location"])
