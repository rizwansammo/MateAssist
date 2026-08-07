"""Development settings. Never used in production - see prod.py."""

from .base import *  # noqa: F403
from .base import REST_FRAMEWORK, env

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", ".localhost", "[::1]"]

# The browsable API is a development affordance only; prod stays JSON-only.
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# Two separate Vite bundles (D-145), plus any tenant subdomain in dev. Regexes
# rather than a fixed list because the tenant subdomain varies per workspace.
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^http://localhost:\d+$",
    r"^http://127\.0\.0\.1:\d+$",
    r"^http://[a-z0-9-]+\.localhost:\d+$",
]
CORS_ALLOW_CREDENTIALS = True  # refresh token travels in an httpOnly cookie (D-032)

CSRF_TRUSTED_ORIGINS = [
    f"http://localhost:{env.int('PORTAL_PORT', default=5175)}",
    f"http://localhost:{env.int('ADMIN_PORT', default=5174)}",
]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
