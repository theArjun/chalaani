"""Settings for chalaani — a chalani (delivery challan) register for Nepali businesses."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = env("DJANGO_SECRET_KEY", "django-insecure-dev-only-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "*").split(",") if h]
CSRF_TRUSTED_ORIGINS = [
    o for o in env("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django_htmx",
    "django_q",
    "accounts",
    "orgs",
    "nepal",
    "chalani",
    "extraction",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "orgs.middleware.CurrentOrganizationMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "orgs.context_processors.organization",
                "nepal.context_processors.nepali_today",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env("DJANGO_DB_PATH", str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {"init_command": "PRAGMA journal_mode=WAL;"},
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "chalani:register"
LOGOUT_REDIRECT_URL = "accounts:login"

# Nepal-specific locale defaults.
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kathmandu"
USE_I18N = True
USE_TZ = True
FIRST_DAY_OF_WEEK = 0  # Sunday — the Nepali week starts on आइतबार.

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploads live OUTSIDE the repo and are never served straight off MEDIA_URL —
# every read goes through chalani.views.chalani_photo, which checks the org.
MEDIA_ROOT = Path(
    env("CHALAANI_MEDIA_ROOT", str(Path.home() / ".chalaani" / "media"))
).expanduser()
MEDIA_URL = None  # deliberately unset: there is no public media URL

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024  # phone photos of paper chalani
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# ---------------------------------------------------------------- background jobs
# `sync: True` runs tasks inline (handy for tests and a bare `runserver`).
# In normal use run `python manage.py qcluster` next to the web process.
Q_CLUSTER = {
    "name": "chalaani",
    "workers": int(env("Q_WORKERS", "2")),
    "timeout": 300,
    "retry": 360,
    "max_attempts": 2,
    "queue_limit": 50,
    "bulk": 1,
    "orm": "default",
    "sync": env_bool("Q_SYNC", False),
    "catch_up": False,
    "save_limit": 200,
}

# ---------------------------------------------------------------- AI extraction
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", "")
EXTRACTION_MODEL = env("CHALAANI_EXTRACTION_MODEL", "claude-opus-5")
EXTRACTION_EFFORT = env("CHALAANI_EXTRACTION_EFFORT", "medium")
EXTRACTION_ENABLED = env_bool("CHALAANI_EXTRACTION_ENABLED", True)

# ---------------------------------------------------------------- front end
# True  -> Tailwind/daisyUI off the CDN (prototyping, zero build step)
# False -> static/css/app.css built by the Tailwind standalone binary (see README)
TAILWIND_CDN = env_bool("CHALAANI_TAILWIND_CDN", True)

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
