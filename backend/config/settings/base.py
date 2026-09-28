"""
Shared Django settings for the School Management System.

All environments import from this module.
"""

import os
import tempfile
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from the backend directory.
load_dotenv(BASE_DIR / ".env")

# SECURITY WARNING: keep the secret key used in production secret!
# No hardcoded fallback: the key MUST come from the environment so that an
# insecure default can never be silently used in a real deployment.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set. Configure it in the environment "
        "or backend/.env — do not rely on a default value."
    )

DEBUG = False

ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS",
    "localhost,127.0.0.1",
).split(",")

INSTALLED_APPS = [
    "apps.accounts",
    "apps.schools",
    "apps.students",
    "apps.teachers",
    "apps.attendance",
    "apps.finance",
    "apps.exams",
    "apps.reportcards",
    "apps.timetable",
    "apps.events",
    "apps.communication",
    "apps.audit",
    "apps.dashboard",
    "apps.ai",

    "apps.library",
    "apps.transport",
    "apps.inventory",
    "apps.payroll",
    "apps.hr",
    "apps.reports",
    "apps.search",
    "apps.documents",
    "apps.discipline",
    "apps.health",
    "apps.alumni",
    "apps.hostel",
    "apps.lms",
    "apps.homework",
    "apps.portal",
    "apps.workflow",
    "apps.white_label",
    "apps.helpdesk",
    "apps.visitors",
    "apps.digital_ids",
    "apps.core",
    "apps.saas",
    # "django_ratelimit",  # Temporarily disabled - requires Redis for production

    "corsheaders",
    "rest_framework",
    "drf_spectacular",

    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.middleware.ContentSecurityPolicyMiddleware",
    # "ratelimit.middleware.RatelimitMiddleware",  # Temporarily disabled for migrations
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.ActiveInstitutionMiddleware",
    "apps.accounts.campus_middleware.CampusAccessMiddleware",
    "apps.schools.middleware.ModuleAccessMiddleware",
    "apps.saas.middleware.UsageTrackingMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.audit.middleware.LoginAttemptAuditMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
database_url = os.environ.get("DATABASE_URL")

if database_url:
    DATABASES = {
        "default": dj_database_url.parse(
            database_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    # Credentials are read strictly from the environment (see backend/.env);
    # no embedded password or username defaults are used.
    required_db_vars = ["DB_ENGINE", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    missing = [v for v in required_db_vars if not os.environ.get(v)]
    if missing:
        raise ImproperlyConfigured(
            "Missing required database settings for the fallback (non-"
            "DATABASE_URL) configuration: "
            + ", ".join(missing)
            + ". Set them in the environment or backend/.env."
        )
    DATABASES = {
        "default": {
            "ENGINE": os.environ["DB_ENGINE"],
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ["DB_USER"],
            "PASSWORD": os.environ["DB_PASSWORD"],
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = os.environ.get(
    "DJANGO_STATIC_ROOT",
    str(BASE_DIR / "staticfiles"),
)

# Media files
MEDIA_URL = "media/"
MEDIA_ROOT = os.environ.get(
    "DJANGO_MEDIA_ROOT",
    str(BASE_DIR / "media"),
)

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    # EmailOrUsernameBackend subclasses ModelBackend, so it alone provides
    # username/email authentication AND admin login (get_user). Keeping the
    # plain ModelBackend in the chain would crash authenticate() with
    # MultipleObjectsReturned as soon as the same username exists in two
    # schools (its get_by_natural_key lookup is unscoped).
    "apps.accounts.authentication.EmailOrUsernameBackend",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": (
        "rest_framework.pagination.PageNumberPagination"
    ),
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        # A school ERP dashboard legitimately issues several API calls per
        # page load; 2000/day caused false throttling for busy admins.
        "user": "10000/day",
        "login": "60/hour",
        "password_reset": "10/hour",
        "email_verify": "10/hour",
        "public_apply": "20/hour",
        # Public transfer-certificate verification: high-entropy 8-char codes,
        # throttled to keep brute-force/enumeration impractical.
        "transfer_certificate_verify": "10/min",
        # 2FA backup-code verification is unauthenticated; throttles
        # brute-force of the 8-char codes and keeps failures uniform.
        "twofa_backup_verify": "10/min",
        # F14: the migration endpoint (core.views.run_migrations_view) is
        # unauthenticated and mutates the schema; throttles the bearer-brute
        # force and keeps failed-auth attempts uniform. Rate is asserted in
        # core/test_migrations.py.
        "run_migrations": "10/min",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
# drf-spectacular settings
SPECTACULAR_SETTINGS = {
    "TITLE": "Perfect Foundation SMS API",
    "DESCRIPTION": "School Management System API documentation",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": True,
    "SORT_OPERATION_PARAMETERS": True,
    "SCHEMA_PATH_PREFIX": "/api/",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
    ],
}


def _csv_env(name):
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


def _bool_env(name, default="1"):
    return os.environ.get(name, default).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


CORS_ALLOW_CREDENTIALS = _bool_env("CORS_ALLOW_CREDENTIALS")
# Must never be "*": the frontend sends credentials, which browsers reject
# when the response origin is a wildcard.
CORS_ALLOWED_ORIGINS = _csv_env("CORS_ALLOWED_ORIGINS") or [
    "https://perfect-foundation-sms.vercel.app",
    "https://perfect-foundation-api.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = False

CSRF_TRUSTED_ORIGINS = [
    "https://*.vercel.app",
    "https://perfect-foundation-sms.vercel.app",
    "https://perfect-foundation-api.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# Cache (for django-ratelimit)
# Use Redis (Upstash/Vercel KV) in production; fall back to local memory cache for development
redis_url = os.environ.get("REDIS_URL") or os.environ.get("UPSTASH_REDIS_URL")
if redis_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": redis_url,
        },
        "ratelimit": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": redis_url,
        },
    }
else:
    CACHE_DIR = os.environ.get("DJANGO_CACHE_DIR", tempfile.gettempdir())
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "default-cache",
        },
        "ratelimit": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ratelimit-cache",
        },
    }

# Email
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    "no-reply@school.local",
)

# Development default: print emails to the console.
# config.settings.production switches to SMTP.
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)

# Twilio SMS
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")

# Stripe Online Payments
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
