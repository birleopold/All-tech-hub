"""Select development or production settings from ``ALLTECH_ENV``."""

import os

if os.getenv("ALLTECH_ENV", "development").lower() == "production":
    from config.settings_production import *  # noqa: F401,F403
else:
    from config.settings_development import *  # noqa: F401,F403

# Request IDs are useful in development, tests and production. Insert the
# middleware once, directly after Django's security middleware, regardless of
# which settings profile was selected above.
_request_context_middleware = "core.middleware.RequestContextMiddleware"
if _request_context_middleware not in MIDDLEWARE:  # noqa: F405
    MIDDLEWARE.insert(1, _request_context_middleware)  # noqa: F405

# Commercial landing pages, buying guides, richer product specifications and
# catalogue-readiness controls are isolated in their own application.
_merchandising_app = "merchandising.apps.MerchandisingConfig"
if _merchandising_app not in INSTALLED_APPS:  # noqa: F405
    INSTALLED_APPS.append(_merchandising_app)  # noqa: F405

_merchandising_context = "merchandising.context_processors.merchandising_context"
_context_processors = TEMPLATES[0]["OPTIONS"]["context_processors"]  # noqa: F405
if _merchandising_context not in _context_processors:
    _context_processors.append(_merchandising_context)

# Keep strict Merchant publication opt-in until catalogue records have been
# reviewed. Once enabled, incomplete products are removed from the feed rather
# than being published with guessed condition, identifiers or delivery data.
MERCHANT_STRICT_READINESS = os.getenv(
    "ALLTECH_MERCHANT_STRICT_READINESS", "0"
).strip().lower() in {"1", "true", "yes", "on"}

# Uganda is the operating context. Keep the environment override for deployments
# that intentionally serve a different locale.
TIME_ZONE = os.getenv("ALLTECH_TIME_ZONE", "Africa/Kampala")
