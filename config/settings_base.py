"""Shared settings for ALLTECH Hub."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


SECRET_KEY = os.getenv("ALLTECH_SECRET_KEY", "django-insecure-local-development-only")
DEBUG = False
ALLOWED_HOSTS = env_list("ALLTECH_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("ALLTECH_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "django.contrib.humanize", "django.contrib.sitemaps", "core", "crm", "catalog",
    "commerce", "billing", "operations", "dashboard", "reports", "portal",
    "purchasing", "messaging", "inventory", "marketing.apps.MarketingConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "marketing.middleware.CampaignAttributionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.StaffRoleRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "core.context_processors.company",
        "commerce.context_processors.cart_summary",
        "marketing.context_processors.social_profiles",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": {
    "ENGINE": os.getenv("ALLTECH_DB_ENGINE", "django.db.backends.sqlite3"),
    "NAME": os.getenv("ALLTECH_DB_NAME", str(BASE_DIR / "db.sqlite3")),
    "USER": os.getenv("ALLTECH_DB_USER", ""),
    "PASSWORD": os.getenv("ALLTECH_DB_PASSWORD", ""),
    "HOST": os.getenv("ALLTECH_DB_HOST", ""),
    "PORT": os.getenv("ALLTECH_DB_PORT", ""),
    "CONN_MAX_AGE": int(os.getenv("ALLTECH_DB_CONN_MAX_AGE", "0")),
}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("ALLTECH_TIME_ZONE", "Africa/Nairobi")
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "staff_dashboard"
LOGOUT_REDIRECT_URL = "home"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14

SECURITY_HEADERS_ENABLED = env_bool("ALLTECH_SECURITY_HEADERS_ENABLED", True)
REFERRER_POLICY = os.getenv("ALLTECH_REFERRER_POLICY", "same-origin")
PERMISSIONS_POLICY = os.getenv(
    "ALLTECH_PERMISSIONS_POLICY",
    "camera=(), microphone=(), geolocation=(), payment=()",
)
CONTENT_SECURITY_POLICY_REPORT_ONLY = env_bool("ALLTECH_CSP_REPORT_ONLY", True)
CONTENT_SECURITY_POLICY = os.getenv(
    "ALLTECH_CONTENT_SECURITY_POLICY",
    (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' https://cdn.jsdelivr.net; "
        "img-src 'self' data: blob:; "
        "font-src 'self' https://cdn.jsdelivr.net data:; "
        "connect-src 'self'; "
        "manifest-src 'self'; "
        "worker-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'self'; "
        "form-action 'self'"
    ),
)

EMAIL_BACKEND = os.getenv(
    "ALLTECH_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.getenv("ALLTECH_DEFAULT_FROM_EMAIL", "no-reply@alltech.local")
EMAIL_HOST = os.getenv("ALLTECH_EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("ALLTECH_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("ALLTECH_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("ALLTECH_EMAIL_PASSWORD", "")
EMAIL_USE_TLS = env_bool("ALLTECH_EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("ALLTECH_EMAIL_USE_SSL", False)
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

ENFORCE_STAFF_ROLES = env_bool("ALLTECH_ENFORCE_STAFF_ROLES", False)
REQUIRE_STAFF_2FA = env_bool("ALLTECH_REQUIRE_STAFF_2FA", False)
LOG_LEVEL = os.getenv("ALLTECH_LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "formatters": {"structured": {
        "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
    }},
    "handlers": {"console": {
        "class": "logging.StreamHandler", "formatter": "structured",
    }},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {"django.request": {
        "handlers": ["console"], "level": "WARNING", "propagate": False,
    }},
}
