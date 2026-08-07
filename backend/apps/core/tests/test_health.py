"""Health endpoint and dependency-check tests.

These run against the real test database rather than mocks, so the pgvector
assertions prove the extension migration actually applied instead of proving a
stub returned the right string. Phase 0 set that precedent (A-006): where a
decision asserts a property, the test exercises the property.
"""

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core import health

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------- endpoint ---


def test_health_is_reachable_without_authentication() -> None:
    """A health endpoint behind auth is useless to a load balancer.

    DRF denies by default (DEFAULT_PERMISSION_CLASSES = IsAuthenticated), so
    this guards the explicit AllowAny opt-out against being lost in a refactor.
    """
    response = APIClient().get(reverse("core:health"))
    assert response.status_code not in (
        401,
        403,
    ), "health must stay public; the AllowAny opt-out in HealthView was lost"


def test_health_payload_shape(client) -> None:
    response = client.get(reverse("core:health"))
    assert response.status_code in (200, 503)

    body = response.json()
    assert body["status"] in (health.OK, health.DEGRADED, health.ERROR)
    assert body["version"]

    names = {c["name"] for c in body["checks"]}
    assert {"database", "pgvector", "redis", "celery_broker"} <= names

    for check in body["checks"]:
        assert check["status"] in (health.OK, health.DEGRADED, health.ERROR)
        assert isinstance(check["required"], bool)
        assert check["detail"]


def test_health_reports_503_only_for_required_failures(client) -> None:
    """The status code is what orchestrators act on, so it must track the
    required/optional distinction rather than raw check counts."""
    response = client.get(reverse("core:health"))
    body = response.json()

    required_failed = any(c["status"] == health.ERROR and c["required"] for c in body["checks"])
    assert response.status_code == (503 if required_failed else 200)


# --------------------------------------------------------------- database ---


def test_database_check_reports_postgres_17() -> None:
    result = health.check_database()
    assert result.status == health.OK, result.detail
    assert "PostgreSQL 17" in result.detail, "D-011 pins PostgreSQL 17"


# --------------------------------------------------------------- pgvector ---


def test_pgvector_extension_installed_by_migration() -> None:
    """D-015: the extension is created by a migration, never by hand.

    Deleting core.0001_enable_pgvector fails this test - which is the point.
    """
    result = health.check_pgvector()
    assert result.status == health.OK, result.detail
    assert "installed" in result.detail


def test_pgvector_extension_present_in_pg_extension() -> None:
    """Assert against the catalogue directly, independent of the health module,
    so a bug in check_pgvector cannot mask a missing extension."""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        row = cur.fetchone()

    assert row is not None, "pgvector is not installed in the test database"
    assert row[0]


def test_vector_column_and_hnsw_index_work_at_configured_dimension() -> None:
    """The behavioural probe: build a real vector column, a real HNSW index at
    the exact D-057 parameters, and run a real cosine query.

    Phase 0's gate proved this against a throwaway database. This proves it
    against the schema Django actually migrates, at the dimension settings
    actually carry - so a mismatch between EMBEDDING_DIM and what PostgreSQL
    will accept surfaces here, not in Phase 5 on a customer's first upload.
    """
    from django.db import connection

    dim = settings.EMBEDDING_DIM
    with connection.cursor() as cur:
        cur.execute(f"CREATE TEMPORARY TABLE probe (id serial PRIMARY KEY, e vector({dim}))")
        cur.execute(
            f"INSERT INTO probe (e) SELECT ARRAY(SELECT 1.0::real "
            f"FROM generate_series(1, {dim}))::vector"
        )
        cur.execute(
            f"INSERT INTO probe (e) SELECT ARRAY(SELECT (CASE WHEN g = 1 THEN 1.0 ELSE 0.0 END)"
            f"::real FROM generate_series(1, {dim}) g)::vector"
        )
        cur.execute(
            f"CREATE INDEX probe_hnsw ON probe USING hnsw (e vector_cosine_ops) "
            f"WITH (m = {settings.HNSW_M}, ef_construction = {settings.HNSW_EF_CONSTRUCTION})"
        )
        cur.execute(
            "SELECT id FROM probe ORDER BY e <=> (SELECT e FROM probe WHERE id = 1) LIMIT 1"
        )
        nearest = cur.fetchone()[0]

    assert nearest == 1, "the <=> cosine operator did not return the expected neighbour"


def test_embedding_dim_is_indexable() -> None:
    """A dimension above pgvector's HNSW ceiling would only surface in Phase 5
    as a failed index build on the first upload. Catch it at test time."""
    assert 0 < settings.EMBEDDING_DIM <= health.HNSW_MAX_DIMENSIONS


def test_embedding_dim_matches_the_locked_decision() -> None:
    """D-060 locks 384 (bge-small-en-v1.5). The dimension is baked into the
    vector() column and the HNSW index, so changing it silently means
    re-embedding every chunk of every tenant. Changing it should require
    changing this test, and therefore reading the decision."""
    assert settings.EMBEDDING_DIM == 384
    assert settings.EMBEDDING_MODEL == "BAAI/bge-small-en-v1.5"


# ------------------------------------------------------------ folding rule ---


@pytest.mark.parametrize(
    ("checks", "expected"),
    [
        ([("database", health.OK, True)], health.OK),
        # An optional dependency being down must not take the service down: a
        # missing Celery worker is normal in dev and during a rolling restart.
        (
            [("database", health.OK, True), ("celery_workers", health.DEGRADED, False)],
            health.DEGRADED,
        ),
        ([("database", health.ERROR, True)], health.ERROR),
        # A required ERROR outranks an optional OK.
        ([("database", health.ERROR, True), ("celery_workers", health.OK, False)], health.ERROR),
    ],
)
def test_overall_status_folding(checks, expected) -> None:
    results = [health.Check(name, status, "x", required=req) for name, status, req in checks]

    if any(c.status == health.ERROR and c.required for c in results):
        overall = health.ERROR
    elif any(c.status in (health.ERROR, health.DEGRADED) for c in results):
        overall = health.DEGRADED
    else:
        overall = health.OK

    assert overall == expected


def test_run_all_returns_every_registered_check() -> None:
    overall, results = health.run_all()
    assert overall in (health.OK, health.DEGRADED, health.ERROR)
    assert len(results) == len(health.CHECKS)
