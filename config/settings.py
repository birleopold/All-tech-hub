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

# Uganda is the operating context. Keep the environment override for deployments
# that intentionally serve a different locale.
TIME_ZONE = os.getenv("ALLTECH_TIME_ZONE", "Africa/Kampala")
