"""Production settings.

Every secret and deployment value is required from the environment. The
application refuses to start when one is missing instead of falling back to an
insecure default.
"""

from .base import *  # noqa: F403 - settings modules intentionally star-import the base
from .base import env, env_bool, env_list

DEBUG = False
SECRET_KEY = env("SECRET_KEY", required=True)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise RuntimeError("ALLOWED_HOSTS must contain at least one host in production.")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", required=True),
        "USER": env("DB_USER", required=True),
        "PASSWORD": env("DB_PASSWORD", required=True),
        "HOST": env("DB_HOST", required=True),
        "PORT": env("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

SWAGGER_ENABLED = env_bool("SWAGGER_ENABLED", False)

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

LOGGING["root"]["level"] = "INFO"  # noqa: F405 - imported from base via star import
