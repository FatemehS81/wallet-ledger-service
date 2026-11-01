"""Development settings: verbose, convenient, never for production."""

import os

from .base import *  # noqa: F403 - settings modules intentionally star-import the base

DEBUG = True
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-secret-key")
ALLOWED_HOSTS = ["*"]

LOGGING["root"]["level"] = "DEBUG"  # noqa: F405 - imported from base via star import
LOGGING["loggers"] = {  # noqa: F405
    "django.db.backends": {
        "handlers": ["console"],
        "level": "INFO",
        "propagate": False,
    },
}
