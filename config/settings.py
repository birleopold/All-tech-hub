"""
Django settings for ALLTECH Hub — IT services & retail operations.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-dev-change-me-in-production"

DEBUG = True

ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1", "testserver", "192.168.100.15"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "core",
    "crm",
    "catalog",
    "commerce",
    "billing",
    "operations",
    "dashboard",
    "reports",
    "portal",
    "purchasing",
    "messaging",
    "inventory",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
                "core.context_processors.company",
                "commerce.context_processors.cart_summary",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "staff_dashboard"
LOGOUT_REDIRECT_URL = "home"

SESSION_COOKIE_AGE = 60 * 60 * 24 * 14

# Email (dev-friendly defaults)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "no-reply@alltech.local"

# Optional SMTP override (set env vars to enable)
EMAIL_HOST = os.getenv("ALLTECH_EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("ALLTECH_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("ALLTECH_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("ALLTECH_EMAIL_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("ALLTECH_EMAIL_USE_TLS", "1") == "1"
EMAIL_USE_SSL = os.getenv("ALLTECH_EMAIL_USE_SSL", "0") == "1"
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
