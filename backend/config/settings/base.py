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
    "corsheaders",
    "drf_spectacular",
    "django_celery_beat",
]

# One app per bounded context. Most are placeholders until their phase lands;
# they exist now so migrations and imports have a stable home and later phases
# only add files rather than restructure.
LOCAL_APPS = [
    "apps.core",           # health, shared utilities              Phase 1
    "apps.tenancy",        # Tenant, Membership, RLS                Phase 2
    "apps.accounts",       # User, auth                             Phase 2
    "apps.helpdesk",       # Ticket, Category, SLA                  Phase 3
    "apps.ai",             # vault, engine clients, router          Phase 4
    "apps.knowledge",      # Document, chunks, ingestion            Phase 5
    "apps.chat",           # Conversation, retrieval, SSE           Phase 6
    "apps.metering",       # UsageEvent, ModelPrice, rollups        Phase 7
    "apps.audit",          # AuditEvent                             Phase 7
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
    # apps.tenancy.middleware.SubdomainMiddleware is inserted here in Phase 2.
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

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
# RLS (D-020) sets app.tenant_id with SET LOCAL, which is transaction-scoped.
# Phase 2 opens an explicit transaction per request rather than relying on
# ATOMIC_REQUESTS, so the tenant variable and the transaction share a lifetime.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=0)

# ------------------------------------------------------- auth / identity ----

# Set before the first migration on purpose. Swapping AUTH_USER_MODEL after
# migrations exist requires destroying the database (D-033).
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
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
UPLOAD_ALLOWED_EXTENSIONS = env.list(
    "UPLOAD_ALLOWED_EXTENSIONS", default=[".pdf", ".docx", ".md"]
)

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
        "django.db.backends": {"level": "WARNING", "propagate": False,
                               "handlers": ["console"]},
    },
}
