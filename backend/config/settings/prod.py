"""Production settings.

Deliberately strict: this module raises at import time if a required secret is
absent, so a misconfigured deploy fails at boot rather than at the first
request that happens to need the value.
"""

from .base import *  # noqa: F403
from .base import env

DEBUG = False

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# Subdomain tenancy needs a wildcard certificate (D-142); TLS terminates at the
# proxy, which forwards the original scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")

X_FRAME_OPTIONS = "DENY"

CORS_ALLOWED_ORIGIN_REGEXES = env.list("CORS_ALLOWED_ORIGIN_REGEXES")
CORS_ALLOW_CREDENTIALS = True

# Reuse connections, but see the D-020 note: if a transaction-pooling PgBouncer
# is ever introduced, the RLS tenant variable must be set inside every
# transaction or isolation breaks silently.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)  # noqa: F405
DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = env(  # noqa: F405
    "DB_SSLMODE", default="require"
)
