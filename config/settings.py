"""Select development or production settings from ``ALLTECH_ENV``."""

import os

if os.getenv("ALLTECH_ENV", "development").lower() == "production":
    from config.settings_production import *  # noqa: F401,F403
else:
    from config.settings_development import *  # noqa: F401,F403

# Uganda is the operating context. Keep the environment override for deployments
# that intentionally serve a different locale.
TIME_ZONE = os.getenv("ALLTECH_TIME_ZONE", "Africa/Kampala")
