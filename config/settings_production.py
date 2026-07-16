"""Production settings; secrets are required through the environment."""

import os

from django.core.exceptions import ImproperlyConfigured

from config.settings_base import *  # noqa: F401,F403

SECRET_KEY = os.getenv("ALLTECH_SECRET_KEY", "")
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("ALLTECH_SECRET_KEY must contain at least 50 characters.")
if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("ALLTECH_ALLOWED_HOSTS must list at least one hostname.")

FIELD_ENCRYPTION_KEY = os.getenv("ALLTECH_FIELD_ENCRYPTION_KEY", SECRET_KEY)
DEBUG = False
ENFORCE_STAFF_ROLES = True
REQUIRE_STAFF_2FA = env_bool("ALLTECH_REQUIRE_STAFF_2FA", True)  # noqa: F405
PRIVATE_MEDIA_USE_X_ACCEL = env_bool(  # noqa: F405
    "ALLTECH_PRIVATE_MEDIA_USE_X_ACCEL",
    True,
)
SECURE_SSL_REDIRECT = env_bool("ALLTECH_SECURE_SSL_REDIRECT", True)  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.getenv("ALLTECH_SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = env_bool("ALLTECH_SECURE_HSTS_PRELOAD", True)  # noqa: F405
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Hashed filenames make long-lived immutable static caching safe after releases.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}
