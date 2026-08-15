# MateAssist backend - Django/ASGI under Uvicorn workers.
#
# Two stages so the runtime image carries no compiler toolchain. The embedding
# model is the reason this image is large: bge-small-en-v1.5 runs locally (D-060)
# rather than through a paid API, which is a deliberate trade - a bigger image
# and no per-query embedding cost or third-party dependency for retrieval.

# ---------------------------------------------------------------- builder ----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# libpq-dev and gcc are needed to build psycopg; they do not travel to runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
# Copy the package tree before installing: the project installs itself (-e .),
# and setuptools needs the modules present to resolve them.
COPY apps ./apps
COPY config ./config
COPY manage.py ./

# Torch is installed FIRST, from the CPU-only index.
#
# sentence-transformers depends on torch, and pip's default wheel is the CUDA
# build: several gigabytes of GPU libraries that this image can never use, since
# neither the CI runner nor the VPS has a GPU. Left to resolve normally it filled
# the GitHub runner's disk and killed the job mid-step - a build that fails with
# no log rather than an error message.
#
# Installing it explicitly from download.pytorch.org/whl/cpu first means the
# dependency is already satisfied when `pip install .` runs, so the CUDA wheel is
# never fetched. Roughly 2GB smaller, and considerably faster to build.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && /opt/venv/bin/pip install .

# ---------------------------------------------------------------- runtime ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    # Keep the model cache on a volume-friendly path. Without this the weights
    # are re-downloaded into a fresh container's home directory on every deploy,
    # adding minutes to the first request after a restart.
    HF_HOME=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/huggingface

# libpq5 is the runtime half of libpq-dev; libmagic and the poppler/mupdf deps
# are used by the ingestion pipeline for content sniffing and PDF parsing.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 libmagic1 curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root. The app writes only to /app/.cache and the media volume, both of
# which are chowned below.
RUN useradd --create-home --uid 10001 mateassist

COPY --from=builder /opt/venv /opt/venv

# Build context is ./backend, matching the builder stage above.
WORKDIR /app
COPY --chown=mateassist:mateassist . /app/

# The volume mount point must exist IN THE IMAGE, owned by the runtime user.
#
# Docker initialises an empty named volume from the image's directory at that
# exact path, ownership included. If the path is absent, Docker creates it as
# root - and a container running as uid 10001 then cannot write there. That is
# not a startup failure: `retrieve()` catches the error and degrades to
# keyword-only search, so the app keeps answering with half its retrieval and
# nothing looks broken. It cost a live deployment before it was noticed.
#
# The full nested path is created, not just /app/.cache, because the mount is at
# /app/.cache/huggingface.
RUN mkdir -p /app/.cache/huggingface /app/media \
    && chown -R mateassist:mateassist /app/.cache /app/media

USER mateassist

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8010/api/v1/health/ || exit 1

# Uvicorn workers under Gunicorn: the chat endpoint streams over SSE (D-003), so
# the worker class must be ASGI. A sync worker would buffer the whole answer and
# deliver it in one lump, which looks like a hang rather than a stream.
CMD ["gunicorn", "config.asgi:application", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "3", \
     "--bind", "0.0.0.0:8010", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
