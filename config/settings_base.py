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


def env_int_list(name: str, default: str) -> tuple[int, ...]:
    values = []
    for item in env_list(name, default):
        try:
            values.append(int(item))
        except (TypeError, ValueError):
            continue
    return tuple(values)


SECRET_KEY = os.getenv("ALLTECH_SECRET_KEY", "django-insecure-local-development-only")
FIELD_ENCRYPTION_KEY = os.getenv("ALLTECH_FIELD_ENCRYPTION_KEY", SECRET_KEY)
DEBUG = False
ALLOWED_HOSTS = env_list("ALLTECH_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("ALLTECH_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "django.contrib.humanize", "django.contrib.sitemaps", "core", "crm", "catalog",
    "commerce.apps.CommerceConfig", "reliability.apps.ReliabilityConfig", "billing", "operations",
    "dashboard", "reports", "portal", "purchasing", "messaging", "inventory",
    "marketing.apps.MarketingConfig", "growth.apps.GrowthConfig",
    "automation.apps.AutomationConfig", "loyalty.apps.LoyaltyConfig",
    "customer_campaigns.apps.CustomerCampaignsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "marketing.middleware.CampaignAttributionMiddleware",
    "growth.middleware.GrowthCommerceMiddleware",
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
        "growth.context_processors.growth_context",
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
PRIVATE_MEDIA_ROOT = Path(
    os.getenv("ALLTECH_PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private_media"))
)
PRIVATE_MEDIA_USE_X_ACCEL = env_bool("ALLTECH_PRIVATE_MEDIA_USE_X_ACCEL", False)
BACKUP_ROOT = Path(os.getenv("ALLTECH_BACKUP_ROOT", str(BASE_DIR / "backups")))
ORDER_RESERVATION_MINUTES = max(
    5,
    int(os.getenv("ALLTECH_ORDER_RESERVATION_MINUTES", "1440")),
)
ORDER_CUSTOMER_EMAILS_ENABLED = env_bool(
    "ALLTECH_ORDER_CUSTOMER_EMAILS_ENABLED",
    True,
)
ORDER_STATUS_EMAILS_ENABLED = env_bool(
    "ALLTECH_ORDER_STATUS_EMAILS_ENABLED",
    True,
)
ORDER_REVIEW_EMAILS_ENABLED = env_bool(
    "ALLTECH_ORDER_REVIEW_EMAILS_ENABLED",
    False,
)
LOYALTY_POINTS_ENABLED = env_bool("ALLTECH_LOYALTY_POINTS_ENABLED", False)
LOYALTY_SPEND_PER_POINT = max(
    1,
    int(os.getenv("ALLTECH_LOYALTY_SPEND_PER_POINT", "10000")),
)
LOYALTY_SILVER_POINTS = max(1, int(os.getenv("ALLTECH_LOYALTY_SILVER_POINTS", "100")))
LOYALTY_GOLD_POINTS = max(
    LOYALTY_SILVER_POINTS,
    int(os.getenv("ALLTECH_LOYALTY_GOLD_POINTS", "500")),
)
LOYALTY_PLATINUM_POINTS = max(
    LOYALTY_GOLD_POINTS,
    int(os.getenv("ALLTECH_LOYALTY_PLATINUM_POINTS", "1500")),
)
PUBLIC_BASE_URL = os.getenv("ALLTECH_PUBLIC_BASE_URL", "https://leosoftug.com").rstrip("/")
CUSTOMER_CAMPAIGN_SEND_ENABLED = env_bool(
    "ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED",
    False,
)
CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER = env_bool(
    "ALLTECH_CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER",
    True,
)
CUSTOMER_CAMPAIGN_MAX_RECIPIENTS = max(
    1,
    min(500, int(os.getenv("ALLTECH_CUSTOMER_CAMPAIGN_MAX_RECIPIENTS", "100"))),
)
CUSTOMER_CAMPAIGN_BATCH_SIZE = max(
    1,
    min(50, int(os.getenv("ALLTECH_CUSTOMER_CAMPAIGN_BATCH_SIZE", "10"))),
)
CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED = env_bool(
    "ALLTECH_CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED",
    False,
)
CUSTOMER_CAMPAIGN_APPROVAL_VALID_HOURS = max(
    1,
    min(720, int(os.getenv("ALLTECH_CUSTOMER_CAMPAIGN_APPROVAL_VALID_HOURS", "48"))),
)
CUSTOMER_CAMPAIGN_SCHEDULE_MAX_LEAD_HOURS = max(
    1,
    min(
        CUSTOMER_CAMPAIGN_APPROVAL_VALID_HOURS,
        int(os.getenv("ALLTECH_CUSTOMER_CAMPAIGN_SCHEDULE_MAX_LEAD_HOURS", "24")),
    ),
)
CUSTOMER_CAMPAIGN_AUTOMATION_BATCH_SIZE = max(
    1,
    min(50, int(os.getenv("ALLTECH_CUSTOMER_CAMPAIGN_AUTOMATION_BATCH_SIZE", "1"))),
)
CUSTOMER_CAMPAIGN_AUTOMATION_INTERVAL_MINUTES = max(
    5,
    min(1440, int(os.getenv("ALLTECH_CUSTOMER_CAMPAIGN_AUTOMATION_INTERVAL_MINUTES", "15"))),
)
CUSTOMER_CAMPAIGN_FAILURE_MIN_ATTEMPTS = max(
    1,
    min(1000, int(os.getenv("ALLTECH_CUSTOMER_CAMPAIGN_FAILURE_MIN_ATTEMPTS", "3"))),
)
CUSTOMER_CAMPAIGN_FAILURE_RATE_PERCENT = max(
    1,
    min(100, int(os.getenv("ALLTECH_CUSTOMER_CAMPAIGN_FAILURE_RATE_PERCENT", "50"))),
)
PRODUCT_IMAGE_RESPONSIVE_ENABLED = env_bool(
    "ALLTECH_PRODUCT_IMAGE_RESPONSIVE_ENABLED",
    True,
)
PRODUCT_IMAGE_RESPONSIVE_WIDTHS = env_int_list(
    "ALLTECH_PRODUCT_IMAGE_RESPONSIVE_WIDTHS",
    "320,640,960,1280",
)
PRODUCT_IMAGE_RESPONSIVE_QUALITY = max(
    60,
    min(95, int(os.getenv("ALLTECH_PRODUCT_IMAGE_RESPONSIVE_QUALITY", "84"))),
)

AUTOMATION_JOB_MAX_ATTEMPTS = max(
    1,
    min(20, int(os.getenv("ALLTECH_AUTOMATION_JOB_MAX_ATTEMPTS", "5"))),
)
AUTOMATION_HTTP_TIMEOUT_SECONDS = max(
    5,
    min(60, int(os.getenv("ALLTECH_AUTOMATION_HTTP_TIMEOUT_SECONDS", "20"))),
)
META_AUTO_PUBLISH_ENABLED = env_bool("ALLTECH_META_AUTO_PUBLISH_ENABLED", False)
META_GRAPH_VERSION = os.getenv("ALLTECH_META_GRAPH_VERSION", "v23.0").strip()
META_PAGE_ID = os.getenv("ALLTECH_META_PAGE_ID", "").strip()
META_INSTAGRAM_ACCOUNT_ID = os.getenv(
    "ALLTECH_META_INSTAGRAM_ACCOUNT_ID", ""
).strip()
META_PAGE_ACCESS_TOKEN = os.getenv("ALLTECH_META_PAGE_ACCESS_TOKEN", "").strip()

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "staff_dashboard"
LOGOUT_REDIRECT_URL = "home"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

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
        "script-src 'self' https://cdn.jsdelivr.net https://www.googletagmanager.com https://www.clarity.ms; "
        "style-src 'self' https://cdn.jsdelivr.net; "
        "img-src 'self' data: blob: https://www.google-analytics.com https://*.google-analytics.com https://c.bing.com; "
        "font-src 'self' https://cdn.jsdelivr.net data:; "
        "connect-src 'self' https://www.google-analytics.com https://*.google-analytics.com https://www.clarity.ms https://*.clarity.ms https://c.bing.com; "
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
