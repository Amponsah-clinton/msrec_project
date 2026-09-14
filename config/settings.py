"""
Django settings for the MSREC project.

Database: SQLite by default for local development. Set DATABASE_URL in .env
to point at the Supabase Postgres instance instead (see .env.example) --
falls back to SQLite automatically whenever DATABASE_URL is unset.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from the project root .env (git-ignored --
# never commit real secrets into this file or into .env).
load_dotenv(BASE_DIR / ".env")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-change-this-in-production")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", "True").strip().lower() in {"1", "true", "yes", "on"}

_allowed_hosts = os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost,.sslip.io")
ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts.split(",") if h.strip()]

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CSRF_TRUSTED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000,https://*.sslip.io",
    ).split(",")
    if o.strip()
]

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "pages",
    "messaging",
    "notifications",
    "payments",
    "reviewer_dashboard",
    "applicant_dashboard",
    "committee_dashboard",
    "chair_dashboard",
    "secretariat_dashboard",
    "admin_dashboard",
]

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "pages:login"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.profile_avatar",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ── Database ─────────────────────────────────────────────────────────────
# SQLite by default. Set DATABASE_URL (see .env.example) to switch to the
# Supabase Postgres instance without touching any code.
_database_url = os.getenv("DATABASE_URL", "").strip()
if _database_url:
    DATABASES = {
        "default": dj_database_url.config(
            default=_database_url,
            conn_max_age=60,
            ssl_require=True,
        )
    }
    # Supabase's pooler can close idle connections; health checks avoid
    # "connection already closed" errors on the next request.
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"].setdefault("connect_timeout", 10)
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ── Email (admin_dashboard replying to Contact-page inquiries) ────────────
# SMTP when EMAIL_HOST is configured in .env; otherwise falls back to the
# console backend (prints the message to the runserver log instead of
# sending it) so replying never crashes just because SMTP isn't set up yet.
_email_host = os.getenv("EMAIL_HOST", "").strip()
if _email_host:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = _email_host
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").strip().lower() in {"1", "true", "yes", "on"}
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "MSREC Secretariat <no-reply@msrec.org>")

# ── Supabase (available for future use: storage, auth, etc.) ──────────────
# Not wired into any view yet -- these are just read from the environment
# so the project is ready to use them when needed.
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")

# ── Paystack (application review-fee payments) ─────────────────────────────
# Test-mode keys by default so the payment gate on the application form
# (applicant_dashboard/views.py + the payments app) works out of the box in
# dev; override with live keys via .env for production. See payments/fees.py
# for the fee schedule and payments/paystack.py for the API calls.
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "sk_test_185fc53d96addab7232060c86f4221918ab59d1c")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "pk_test_af37d26c0fa360522c4e66495f3877e498c18850")

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── Static & media files ───────────────────────────────────────────────────
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

if not DEBUG:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
