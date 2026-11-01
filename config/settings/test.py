"""Test settings: fast, isolated and safe to run anywhere.

The database host and port come from environment variables so the same module
works with the local test compose file and with the CI service container.
"""

import os

from .base import *  # noqa: F403 - settings modules intentionally star-import the base

DEBUG = False
SECRET_KEY = "test-insecure-secret-key-change-me-1234567890"
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "wallet_test"),
        "USER": os.environ.get("DB_USER", "wallet"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "wallet"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5433"),
        "CONN_MAX_AGE": 0,
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LOGGING["root"]["level"] = "WARNING"  # noqa: F405 - imported from base via star import
