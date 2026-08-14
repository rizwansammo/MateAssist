"""Shared Django settings.

Every environment-specific value is read from the repo-root .env, which is the
single source of truth shared by Django, Celery and docker compose. Nothing here
hardcodes a credential, a port or a model id.
"""

from pathlib import Path

import environ

# base.py -> settings -> config -> backend -> repo root
BASE_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = Path(__file__).resolve().parents[3]

env = environ.Env()
environ.Env.read_env(ROOT_DIR / ".env")

# ---------------------------------------------------------------- core ------

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Tenants are resolved from the subdomain (D-021), so the bare domain is only
# ever the platform/admin surface.
BASE_DOMAIN = env("BASE_DOMAIN", default="localhost:8000")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"  # D-003

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------- apps ------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    "django_celery_beat",
]

# One app per bounded context. Most are placeholders until their phase lands;
# they exist now so migrations and imports have a stable home and later phases
# only add files rather than restructure.
LOCAL_APPS = [
    "apps.core",  # health, shared utilities              Phase 1
    "apps.tenancy",  # Tenant, Membership, RLS                Phase 2
    "apps.accounts",  # User, auth                             Phase 2
    "apps.helpdesk",  # Ticket, Category, SLA                  Phase 3
    "apps.ai",  # vault, engine clients, router          Phase 4
    "apps.knowledge",  # Document, chunks, ingestion            Phase 5
    "apps.chat",  # Conversation, retrieval, SSE           Phase 6
    "apps.metering",  # UsageEvent, ModelPrice, rollups        Phase 7
    "apps.audit",  # AuditEvent                             Phase 7
    "apps.platformadmin",  # super-admin-only API surface           Phase 4+
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Last, so request.user is already resolved and the tenant transaction wraps
    # only view work rather than session/auth queries.
    "apps.tenancy.middleware.SubdomainMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ------------------------------------------------------------ database ------

# Two aliases onto the same database, differing only in the role they connect as
# (D-020). This split is what makes RLS real rather than decorative:
#
#   default -> mateassist_app, NOSUPERUSER. All tenant traffic. Subject to policy.
#   admin   -> POSTGRES_USER, superuser/owner. Migrations and the platform-admin
#              surface, which must legitimately see across tenants.
#
# PostgreSQL exempts superusers from RLS unconditionally, so running the app as
# the owner would leave every policy in place and enforcing nothing.
DATABASES = {
    "default": env.db("DATABASE_APP_URL"),
    "admin": env.db("DATABASE_URL"),
}
for _alias in DATABASES:
    DATABASES[_alias]["ATOMIC_REQUESTS"] = False
    # SubdomainMiddleware opens an explicit transaction per request so the
    # transaction-scoped app.tenant_id and the work share a lifetime.
    DATABASES[_alias]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=0)

# Migrations create policies and must run as the owner:
#     manage.py migrate --database=admin
MIGRATION_DATABASE = "admin"

# Both aliases address the same physical database, so the test runner must not
# try to build a second one for `admin`. MIRROR keeps the alias pointed at the
# default test database while retaining its own (owner) credentials.
DATABASES["admin"]["TEST"] = {"MIRROR": "default"}

# ------------------------------------------------------- auth / identity ----

# Set before the first migration on purpose. Swapping AUTH_USER_MODEL after
# migrations exist requires destroying the database (D-033).
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ------------------------------------------------------------ rest api ------

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    # Deny by default. Every public endpoint opts out explicitly.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 25,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "MateAssist API",
    "DESCRIPTION": "Multi-tenant agentic IT helpdesk. DeepSeek reasons over text; "
    "Gemini describes images. See docs/DECISIONS.md.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
}

# ---------------------------------------------------------------- jwt -------

from datetime import timedelta  # noqa: E402

# D-031/D-032: short access token held in memory by the SPA, long refresh token
# in an httpOnly cookie the JS never touches. Rotation + blacklist means a
# stolen refresh token is usable at most once before it is invalidated.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

REFRESH_COOKIE_NAME = "mateassist_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"
REFRESH_COOKIE_SAMESITE = "Lax"
REFRESH_COOKIE_SECURE = not DEBUG

# ---------------------------------------------------------- escalation ------

# A-008: MateAssist stores no tickets. When the agent cannot resolve an issue it
# emails the transcript to the workspace's existing helpdesk.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="mateassist@localhost")

# Used when a tenant has no support_email of its own (D-128).
DEFAULT_SUPPORT_EMAIL = env("DEFAULT_SUPPORT_EMAIL", default="")

# ------------------------------------------------------------- celery -------

CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
# Ingestion tasks are long and fan-out shaped; late ack means a worker crash
# re-queues the task instead of silently dropping a runbook mid-parse.
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

REDIS_URL = env("REDIS_URL")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# ------------------------------------------------------------- ai/rag -------

# Model ids are configuration, never constants (D-045). A provider deprecation
# is an .env change, not a refactor.
DEEPSEEK_API_BASE = env("DEEPSEEK_API_BASE", default="https://api.deepseek.com")
DEEPSEEK_MODEL_CHAT = env("DEEPSEEK_MODEL_CHAT", default="deepseek-chat")
DEEPSEEK_MODEL_REASONER = env("DEEPSEEK_MODEL_REASONER", default="deepseek-reasoner")
GEMINI_MODEL_VISION = env("GEMINI_MODEL_VISION", default="gemini-2.5-flash")

EMBEDDING_MODEL = env("EMBEDDING_MODEL", default="BAAI/bge-small-en-v1.5")
# Baked into the vector() column and the HNSW index. Changing the model without
# changing this corrupts retrieval silently (D-060).
EMBEDDING_DIM = env.int("EMBEDDING_DIM", default=384)
EMBEDDING_QUERY_PREFIX = env(
    "EMBEDDING_QUERY_PREFIX",
    default="Represent this sentence for searching relevant passages:",
)

CHUNK_TARGET_TOKENS = env.int("CHUNK_TARGET_TOKENS", default=512)
CHUNK_OVERLAP_RATIO = env.float("CHUNK_OVERLAP_RATIO", default=0.15)
RETRIEVAL_TOP_K = env.int("RETRIEVAL_TOP_K", default=20)
RETRIEVAL_RRF_K = env.int("RETRIEVAL_RRF_K", default=60)
RETRIEVAL_TOP_N = env.int("RETRIEVAL_TOP_N", default=6)

# Relevance gating (D-138). Two levels, not one.
#
# MEASURED, not chosen. `manage.py retrieval_probe` scored ten greetings and ten
# support requests against the five-document corpus:
#
#     small talk     0.452 .. 0.524   (median 0.495)
#     real questions 0.557 .. 0.743   (median 0.706)
#
# CITE sits at the midpoint of that gap; GROUND sits just above the small-talk
# ceiling. GROUND is the looser of the two on purpose: a wrong guess there costs
# the user a correct answer, while a wrong guess at CITE costs a chip on screen.
#
# **The gap narrows as the corpus grows** - it was 0.055 with one document and
# 0.033 with five, because more chunks means more chance that something sits
# coincidentally close to a greeting. This is the number to watch. Re-run
# `retrieval_probe` after any significant upload, and if the ranges ever overlap,
# a fixed threshold is no longer the right mechanism.
RETRIEVAL_GROUND_MIN = env.float("RETRIEVAL_GROUND_MIN", default=0.53)
RETRIEVAL_CITE_MIN = env.float("RETRIEVAL_CITE_MIN", default=0.54)

# Document focus (D-139). How far ahead the best-matching document must be
# before the others are dropped entirely.
#
# Retrieval returns the best CHUNKS, not the best document, so a VPN question
# can pull passages from two different VPN runbooks at once - and a model asked
# to answer from that material will write one tidy procedure out of two
# incompatible ones. Every step true, the combination fiction.
#
# Above this margin the runner-up is discarded before the model sees it, so
# blending is impossible rather than discouraged. Below it the question is
# genuinely ambiguous, both documents are kept, and the prompt tells the model
# they are separate sources that must not be merged.
RETRIEVAL_FOCUS_MARGIN = env.float("RETRIEVAL_FOCUS_MARGIN", default=0.04)
HNSW_M = env.int("HNSW_M", default=16)
HNSW_EF_CONSTRUCTION = env.int("HNSW_EF_CONSTRUCTION", default=64)

# ------------------------------------------------------------- vault --------

# AES-256-GCM KEK for provider credentials (D-071). Never logged, never returned.
MATEASSIST_VAULT_KEY = env("MATEASSIST_VAULT_KEY")

# ------------------------------------------------------------ storage -------

S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", default="")
S3_BUCKET_NAME = env("S3_BUCKET_NAME", default="mateassist-documents")
S3_ACCESS_KEY_ID = env("S3_ACCESS_KEY_ID", default="")
S3_SECRET_ACCESS_KEY = env("S3_SECRET_ACCESS_KEY", default="")
S3_REGION = env("S3_REGION", default="us-east-1")

UPLOAD_MAX_BYTES = env.int("UPLOAD_MAX_BYTES", default=52428800)
UPLOAD_ALLOWED_EXTENSIONS = env.list("UPLOAD_ALLOWED_EXTENSIONS", default=[".pdf", ".docx", ".md"])

# ---------------------------------------------------------- i18n/static -----

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"

# ------------------------------------------------------------ logging -------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "propagate": False, "handlers": ["console"]},
    },
}
