"""Project-wide invariants: privacy, tenancy at the URL level, and the catalog.

These are the promises the README makes, asserted rather than assumed.
"""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import get_resolver, reverse
from django.utils import translation


def _named_routes(resolver, prefix=""):
    from django.urls import URLPattern, URLResolver

    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            namespace = f"{prefix}{pattern.namespace}:" if pattern.namespace else prefix
            yield from _named_routes(pattern, namespace)
        elif isinstance(pattern, URLPattern) and pattern.name:
            yield prefix + pattern.name


def no_argument_urls():
    """Every named route that can be reversed without arguments."""
    from django.urls.exceptions import NoReverseMatch

    seen = set()
    for name in _named_routes(get_resolver()):
        if name in seen:
            continue
        seen.add(name)
        try:
            yield name, reverse(name)
        except NoReverseMatch:
            continue


class MediaPrivacyTests(TestCase):
    def test_there_is_no_public_media_url(self):
        """Photos are served only by an org-checked view."""
        self.assertIsNone(settings.MEDIA_URL)

    def test_uploads_live_outside_the_repository(self):
        media_root = Path(settings.MEDIA_ROOT).resolve()
        self.assertFalse(
            str(media_root).startswith(str(Path(settings.BASE_DIR).resolve())),
            f"MEDIA_ROOT {media_root} is inside the repo",
        )

    def test_the_only_media_route_is_the_org_checked_one(self):
        routes = [url for _name, url in no_argument_urls()]
        self.assertFalse([url for url in routes if url.startswith("/media")])


class TenancySettingsTests(TestCase):
    def test_the_current_organization_middleware_runs_after_authentication(self):
        order = settings.MIDDLEWARE
        self.assertLess(
            order.index("django.contrib.auth.middleware.AuthenticationMiddleware"),
            order.index("orgs.middleware.CurrentOrganizationMiddleware"),
        )

    def test_the_project_uses_its_own_user_model(self):
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.User")

    def test_the_organization_is_available_to_every_template(self):
        processors = settings.TEMPLATES[0]["OPTIONS"]["context_processors"]
        self.assertIn("orgs.context_processors.organization", processors)


class LocaleSettingsTests(TestCase):
    def test_nepali_is_the_default_and_english_is_offered(self):
        self.assertEqual(settings.LANGUAGE_CODE, "ne")
        self.assertEqual([code for code, _label in settings.LANGUAGES], ["ne", "en"])

    def test_the_locale_middleware_can_switch_the_language(self):
        self.assertIn("django.middleware.locale.LocaleMiddleware", settings.MIDDLEWARE)
        self.assertTrue(settings.USE_I18N)

    def test_dates_are_kept_in_nepal_time(self):
        self.assertEqual(settings.TIME_ZONE, "Asia/Kathmandu")
        self.assertEqual(settings.FIRST_DAY_OF_WEEK, 0)  # आइतबार


class MessageCatalogTests(TestCase):
    """Shipping an untranslated string means a Nepali user reads English."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.catalog = Path(settings.BASE_DIR) / "locale/ne/LC_MESSAGES/django.po"
        cls.text = cls.catalog.read_text(encoding="utf-8")
        cls.blocks = [b for b in cls.text.split("\n\n") if "msgid" in b]

    def test_the_nepali_catalog_is_committed(self):
        self.assertTrue(self.catalog.exists())
        self.assertTrue(self.catalog.with_suffix(".mo").exists(), "run compilemessages")

    def test_nothing_is_left_untranslated(self):
        missing = [
            block
            for block in self.blocks
            if re.search(r'^msgid "(?!")', block, re.M)
            and re.search(r'^msgstr ""\s*$', block, re.M)
        ]
        self.assertEqual(missing, [], "untranslated msgids in locale/ne")

    def test_nothing_is_left_fuzzy(self):
        self.assertNotIn("#, fuzzy", self.text)

    def test_the_catalog_actually_reaches_the_translation_machinery(self):
        with translation.override("ne"):
            self.assertEqual(translation.gettext("Draft"), "मस्यौदा")
        with translation.override("en"):
            self.assertEqual(translation.gettext("Draft"), "Draft")


class UrlSurfaceTests(TestCase):
    """No page of the register answers a stranger."""

    def setUp(self):
        self.public = {
            reverse("accounts:login"),
            reverse("accounts:signup"),
            reverse("set_language"),
        }

    def test_every_register_page_sends_an_anonymous_visitor_to_the_login(self):
        for name, url in no_argument_urls():
            if url in self.public or url.startswith("/admin"):
                continue
            response = self.client.get(url)
            self.assertIn(
                response.status_code, {302, 405}, f"{name} ({url}) answered anonymously"
            )
            if response.status_code == 302:
                self.assertIn("/accounts/login/", response["Location"], name)

    def test_a_signed_in_user_with_no_firm_is_never_shown_a_500(self):
        user = get_user_model().objects.create_user(
            username="loner", password="pw12345678"
        )
        self.client.force_login(user)
        for name, url in no_argument_urls():
            if url.startswith("/admin") or url == reverse("set_language"):
                continue
            response = self.client.get(url)
            self.assertLess(response.status_code, 500, f"{name} ({url}) blew up")

    def test_the_login_and_signup_pages_are_public(self):
        for url in (reverse("accounts:login"), reverse("accounts:signup")):
            self.assertEqual(self.client.get(url).status_code, 200, url)


class AdminTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="root", password="pw12345678", email="root@example.com"
        )
        self.client.force_login(self.admin)

    def test_every_registered_model_has_a_working_changelist(self):
        from django.contrib import admin

        for model, _model_admin in admin.site._registry.items():
            url = reverse(
                f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist"
            )
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_the_register_is_administrable(self):
        from chalani.models import Chalani, Item, Vendor
        from django.contrib import admin

        for model in (Chalani, Vendor, Item):
            self.assertIn(model, admin.site._registry)

    def test_the_admin_is_closed_to_everyone_else(self):
        self.client.force_login(
            get_user_model().objects.create_user(username="clerk", password="pw12345678")
        )
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)


class TemplateFilterTests(TestCase):
    def test_the_nepali_filters_are_registered_under_the_names_templates_use(self):
        from nepal.templatetags.nepal import register

        expected = {
            "bs", "bs_date", "bs_date_long", "fy", "num", "money", "qty",
            "in_words", "unit_label", "status_badge", "ago",
        }
        self.assertTrue(expected <= set(register.filters))
        self.assertTrue({"today_bs", "current_fiscal_year"} <= set(register.tags))

    def test_a_status_chip_class_is_produced_for_every_status(self):
        from chalani.models import Chalani
        from nepal.templatetags.nepal import status_badge

        for status, _label in Chalani.Status.choices:
            self.assertEqual(status_badge(status), f"chip chip-{status}")
        self.assertEqual(status_badge("nonsense"), "chip chip-draft")


class DeploymentEntryPointTests(TestCase):
    """The two files a production server imports have to import cleanly."""

    def test_the_wsgi_application_is_importable(self):
        from config.wsgi import application

        self.assertTrue(callable(application))

    def test_the_asgi_application_is_importable(self):
        from config.asgi import application

        self.assertTrue(callable(application))

    def test_sqlite_runs_in_wal_mode(self):
        options = settings.DATABASES["default"]["OPTIONS"]
        self.assertIn("WAL", options["init_command"])

    def test_background_work_is_queued_through_the_orm_not_redis(self):
        self.assertEqual(settings.Q_CLUSTER["orm"], "default")


class ProductionSettingsTests(TestCase):
    """`DJANGO_DEBUG=0` has to turn the deployment hardening on by itself."""

    @staticmethod
    def load_settings(environment):
        """Execute config/settings.py in isolation under a given environment."""
        import importlib.util
        import os
        from unittest import mock

        path = Path(settings.BASE_DIR) / "config" / "settings.py"
        spec = importlib.util.spec_from_file_location("config._settings_probe", path)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, environment, clear=False):
            spec.loader.exec_module(module)
        return module

    def test_production_secures_the_cookies_and_trusts_the_proxy_header(self):
        production = self.load_settings({"DJANGO_DEBUG": "0"})
        self.assertFalse(production.DEBUG)
        self.assertTrue(production.SESSION_COOKIE_SECURE)
        self.assertTrue(production.CSRF_COOKIE_SECURE)
        self.assertTrue(production.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(
            production.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https")
        )

    def test_development_does_not_demand_https_cookies(self):
        development = self.load_settings({"DJANGO_DEBUG": "1"})
        self.assertTrue(development.DEBUG)
        self.assertFalse(getattr(development, "SESSION_COOKIE_SECURE", False))

    def test_media_stays_private_in_production_too(self):
        self.assertIsNone(self.load_settings({"DJANGO_DEBUG": "0"}).MEDIA_URL)

    def test_the_tailwind_switch_reads_the_usual_spellings(self):
        from config.settings import env_bool
        import os
        from unittest import mock

        for raw, expected in {
            "1": True, "true": True, "YES": True, "on": True,
            "0": False, "false": False, "no": False, "": False,
        }.items():
            with mock.patch.dict(os.environ, {"CHALAANI_PROBE": raw}):
                self.assertIs(env_bool("CHALAANI_PROBE"), expected, raw)
        self.assertIs(env_bool("CHALAANI_NOT_SET_AT_ALL", True), True)
