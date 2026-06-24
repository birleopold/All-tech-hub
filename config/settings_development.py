"""Local development and test settings."""

from config.settings_base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = env_list(  # noqa: F405
    "ALLTECH_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver,192.168.100.15"
)
