"""Dependency health checks.

Each check exercises the dependency for real - a query, a PING, a broker
handshake - rather than reporting on configuration. Phase 0 established the
principle after a bucket-privacy assertion passed on a string match while
proving nothing (A-006); the same rule applies here.

Checks marked required=False can fail without failing the endpoint. A Celery
worker being offline is normal on a dev machine and must not read as an outage.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import connection

OK = "ok"
DEGRADED = "degraded"
ERROR = "error"

# pgvector's HNSW index cannot be built above this many dimensions.
HNSW_MAX_DIMENSIONS = 2000

# The Celery worker probe is a broadcast: it costs its timeout plus mailbox
# setup on every call (~770ms measured), which is far too slow for an endpoint
# a load balancer polls. The result is cached so repeated probes are free while
# staying fresh enough to notice a worker dropping out.
WORKER_PING_TIMEOUT_SECONDS = 0.4
WORKER_CACHE_KEY = "health:celery_workers"
WORKER_CACHE_TTL_SECONDS = 15


@dataclass
class Check:
    name: str
    status: str
    detail: str
    latency_ms: float | None = None
    required: bool = True
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not payload["meta"]:
            payload.pop("meta")
        return payload


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


def check_database() -> Check:
    """Round-trip a real query and report the server version."""
    started = time.perf_counter()
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.execute("SHOW server_version")
            version = cur.fetchone()[0]
    except Exception as exc:
        return Check("database", ERROR, f"unreachable: {exc}", _elapsed_ms(started))

    major = version.split(".")[0]
    if major != "17":
        return Check(
            "database",
            DEGRADED,
            f"expected PostgreSQL 17, found {version} (D-011)",
            _elapsed_ms(started),
        )
    return Check("database", OK, f"PostgreSQL {version}", _elapsed_ms(started))


def check_pgvector() -> Check:
    """Confirm the extension is installed, and that EMBEDDING_DIM is indexable.

    A dimension above pgvector's HNSW ceiling would only surface in Phase 5 as a
    failed index build on the first upload, so it is validated here instead.
    """
    started = time.perf_counter()
    dim = settings.EMBEDDING_DIM
    meta = {"embedding_model": settings.EMBEDDING_MODEL, "embedding_dim": dim}

    try:
        with connection.cursor() as cur:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            installed = cur.fetchone()
            if installed is None:
                cur.execute(
                    "SELECT default_version FROM pg_available_extensions "
                    "WHERE name = 'vector'"
                )
                available = cur.fetchone()
                detail = (
                    f"available ({available[0]}) but not created - run migrate"
                    if available
                    else "not available in this PostgreSQL build"
                )
                return Check("pgvector", ERROR, detail, _elapsed_ms(started), meta=meta)
            version = installed[0]
    except Exception as exc:
        return Check("pgvector", ERROR, f"query failed: {exc}", _elapsed_ms(started), meta=meta)

    if dim > HNSW_MAX_DIMENSIONS:
        return Check(
            "pgvector",
            ERROR,
            f"EMBEDDING_DIM={dim} exceeds the HNSW limit of {HNSW_MAX_DIMENSIONS}",
            _elapsed_ms(started),
            meta=meta,
        )
    return Check("pgvector", OK, f"extension {version} installed", _elapsed_ms(started), meta=meta)


def check_redis() -> Check:
    """PING the cache/broker instance."""
    started = time.perf_counter()
    try:
        import redis

        client = redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2
        )
        if not client.ping():
            return Check("redis", ERROR, "PING returned falsy", _elapsed_ms(started))
        info = client.info("server")
        version = info.get("redis_version", "unknown")
    except Exception as exc:
        return Check("redis", ERROR, f"unreachable: {exc}", _elapsed_ms(started))
    return Check("redis", OK, f"PONG from Redis {version}", _elapsed_ms(started))


def check_celery_broker() -> Check:
    """Verify the broker accepts a connection.

    Broker reachability is required; a worker being attached is not - see
    check_celery_workers.
    """
    started = time.perf_counter()
    try:
        from config.celery import app as celery_app

        conn = celery_app.connection()
        try:
            conn.ensure_connection(max_retries=0, timeout=3)
        finally:
            conn.release()
    except Exception as exc:
        return Check("celery_broker", ERROR, f"unreachable: {exc}", _elapsed_ms(started))
    return Check("celery_broker", OK, "broker connection established", _elapsed_ms(started))


def check_celery_workers() -> Check:
    """Report attached workers. Informational: absence is not an outage.

    control.ping is a broadcast that waits for replies, so this check costs its
    full timeout whenever no worker is attached. Kept deliberately short - this
    endpoint gets polled by load balancers, and a slow health check is its own
    kind of outage.
    """
    started = time.perf_counter()

    # A cache miss must never be fatal - if Redis is down the redis check
    # already reports it, and this check should still attempt a live probe.
    try:
        cached = cache.get(WORKER_CACHE_KEY)
    except Exception:
        cached = None
    if cached is not None:
        check = Check(**cached)
        check.latency_ms = _elapsed_ms(started)
        check.meta = {**check.meta, "cached": True, "cache_ttl_s": WORKER_CACHE_TTL_SECONDS}
        return check

    try:
        from config.celery import app as celery_app

        replies = celery_app.control.ping(timeout=WORKER_PING_TIMEOUT_SECONDS) or []
    except Exception as exc:
        return Check(
            "celery_workers", DEGRADED, f"could not query: {exc}",
            _elapsed_ms(started), required=False,
        )

    if not replies:
        result = Check(
            "celery_workers",
            DEGRADED,
            "no workers attached - ingestion tasks will queue",
            required=False,
        )
    else:
        names = sorted(name for reply in replies for name in reply)
        result = Check(
            "celery_workers", OK, f"{len(names)} worker(s): {', '.join(names)}",
            required=False,
        )

    try:
        cache.set(WORKER_CACHE_KEY, asdict(result), WORKER_CACHE_TTL_SECONDS)
    except Exception:
        pass  # caching is an optimisation, never a correctness requirement

    result.latency_ms = _elapsed_ms(started)
    return result


CHECKS = (
    check_database,
    check_pgvector,
    check_redis,
    check_celery_broker,
    check_celery_workers,
)


def run_all() -> tuple[str, list[Check]]:
    """Run every check and fold the results into one overall status."""
    results = [check() for check in CHECKS]

    if any(c.status == ERROR and c.required for c in results):
        overall = ERROR
    elif any(c.status in (ERROR, DEGRADED) for c in results):
        overall = DEGRADED
    else:
        overall = OK
    return overall, results
