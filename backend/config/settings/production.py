import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import CSRF_COOKIE_SAMESITE, MIDDLEWARE, SESSION_COOKIE_SAMESITE

DEBUG = False

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a secure value in production."
    )

def _clean_host(value):
    """Accept bare hostnames or full origins and return a bare hostname."""
    host = value.strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    return host.split("/", 1)[0]


ALLOWED_HOSTS = []
for _raw in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(","):
    _host = _clean_host(_raw)
    if _host and _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)
for _fallback in (".vercel.app", "localhost", "127.0.0.1"):
    if _fallback not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_fallback)

# Merge code defaults (base.py) with env-provided origins and the Vercel hosts.
_VERCEL_DEFAULT_ORIGINS = [
    "https://perfect-foundation-backend.vercel.app",
    "https://perfect-foundation-sms.vercel.app",
]
_env_origins = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
CSRF_TRUSTED_ORIGINS = list(
    dict.fromkeys(
        [
            *CSRF_TRUSTED_ORIGINS,
            *_VERCEL_DEFAULT_ORIGINS,
            *_env_origins,
        ]
    )
)

SESSION_COOKIE_SECURE = (
    os.environ.get("DJANGO_SESSION_COOKIE_SECURE", "1") == "1"
)
CSRF_COOKIE_SECURE = (
    os.environ.get("DJANGO_CSRF_COOKIE_SECURE", "1") == "1"
)

# 14-day session lifetime; do not expire on browser close.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_HTTPONLY = True

# The frontend reads the csrf token from document.cookie and sends
# it back as the X-CSRFToken header, so it must not be HttpOnly.
CSRF_COOKIE_HTTPONLY = False
# Cross-site credentialed requests from the Vercel frontend require
# SameSite=None; both cookies are already Secure=True in production.
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "None")
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "None")

SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

# Set to 0 when testing locally over plain HTTP (no terminating proxy).
SECURE_SSL_REDIRECT = (
    os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "1") == "1"
)

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# =============================================================================
# Hardening: env-controlled referrer/cross-origin policy. The browser caches
# HSTS for a year, so these are gated behind env flags for a clean rollout.
# =============================================================================
SECURE_REFERRER_POLICY = os.environ.get(
    "DJANGO_SECURE_REFERRER_POLICY", "same-origin"
).strip() or "same-origin"

if os.environ.get("DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY") == "same-origin":
    SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

if os.environ.get("SECURE_CONTENT_TYPE_NOSNIFF", "1") == "1":
    SECURE_CONTENT_TYPE_NOSNIFF = True

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE,
]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

# Use Vercel Blob storage when the connection token is present (production,
# preview and development environments on Vercel). Otherwise keep the local
# FileSystemStorage for local development.
if os.environ.get("BLOB_READ_WRITE_TOKEN"):
    STORAGES["default"] = {
        "BACKEND": "config.blob_storage.VercelBlobStorage",
    }
else:
    STORAGES["default"] = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    }

MEDIA_URL = "media/"
MEDIA_ROOT = os.environ.get(
    "DJANGO_MEDIA_ROOT",
    str(BASE_DIR / "media"),
)

# Transactional email via SMTP (set the DJANGO_EMAIL_* variables).
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("DJANGO_EMAIL_USE_TLS", "1") == "1"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
