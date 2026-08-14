"""Access control on the reporting surfaces.

The platform endpoints read on a connection that bypasses RLS. `IsPlatformOwner`
is therefore the *only* thing between those responses and every workspace's
figures - so it is tested as a security control, not as a detail.
"""

import json
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.ai.models import Engine
from apps.metering.models import Operation, UsageEvent
from apps.tenancy.models import Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

pytestmark = pytest.mark.django_db(databases=["default", "admin"])

User = get_user_model()


@pytest.fixture
def world():
    alpha = Tenant.objects.create(name="Alpha", slug="alpha")
    beta = Tenant.objects.create(name="Beta", slug="beta")

    owner = User.objects.create_user("owner@platform.test", "correct-horse-battery")
    admin_a = User.objects.create_user("admin@alpha.test", "correct-horse-battery")
    user_a = User.objects.create_user("user@alpha.test", "correct-horse-battery")

    Membership.all_objects.create(user=owner, tenant=None, role=Role.PLATFORM_OWNER)
    set_db_tenant(alpha.id)
    Membership.all_objects.create(user=admin_a, tenant=alpha, role=Role.TENANT_ADMIN)
    Membership.all_objects.create(user=user_a, tenant=alpha, role=Role.END_USER)

    UsageEvent.all_objects.create(
        tenant=alpha,
        engine=Engine.TEXT,
        model="gemini-flash-latest",
        operation=Operation.CHAT,
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=Decimal("1.50"),
    )
    set_db_tenant(beta.id)
    UsageEvent.all_objects.create(
        tenant=beta,
        engine=Engine.TEXT,
        model="gemini-flash-latest",
        operation=Operation.CHAT,
        prompt_tokens=999,
        completion_tokens=999,
        cost_usd=Decimal("99.00"),
    )
    set_db_tenant(None)

    return {"alpha": alpha, "beta": beta, "owner": owner, "admin_a": admin_a, "user_a": user_a}


def client_for(user, tenant=None):
    """A client bound to a host.

    The Host header is how the backend resolves a tenant (A-007), so a tenant
    request must carry `<slug>.localhost` and a platform request must not carry
    a tenant host at all - `IsPlatformOwner` refuses anyone signed in on a
    workspace subdomain.
    """
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = f"{tenant.slug}.localhost" if tenant else "localhost"
    return client


# ------------------------------------------------------- platform surface ----


def test_platform_usage_requires_platform_owner(world):
    response = client_for(world["admin_a"], world["alpha"]).get("/api/v1/platform/usage/")
    assert response.status_code == 403


def test_platform_usage_refuses_an_anonymous_caller():
    assert APIClient().get("/api/v1/platform/usage/").status_code in (401, 403)


def test_platform_spend_is_reachable_by_an_owner(world):
    """Authorisation only. The figures are empty here because the platform alias
    is a separate connection that cannot see this test's uncommitted rows; the
    real numbers are asserted in test_platform_rollups.py, which commits."""
    response = client_for(world["owner"]).get("/api/v1/platform/spend/")

    assert response.status_code == 200
    assert "tenants" in response.data and "totals" in response.data


def test_platform_logs_require_platform_owner(world):
    assert (
        client_for(world["admin_a"], world["alpha"]).get("/api/v1/platform/logs/").status_code
        == 403
    )


def test_budgets_are_not_reachable_by_a_workspace_admin(world):
    """A workspace must not be able to read - let alone raise - its own cap."""
    response = client_for(world["admin_a"], world["alpha"]).get("/api/v1/platform/budgets/")
    assert response.status_code == 403


# --------------------------------------------------------- tenant surface ----


def test_workspace_admin_sees_only_their_own_usage(world):
    response = client_for(world["admin_a"], world["alpha"]).get("/api/v1/usage/summary/")

    assert response.status_code == 200
    # Beta spent $99. If any of it appears here, RLS or the filter has failed.
    assert response.data["totals"]["cost_usd"] == "1.500000"
    assert response.data["totals"]["requests"] == 1


def test_an_end_user_cannot_see_workspace_spend(world):
    """Stricter than the runbook surface on purpose: volume and spend say how
    the business is being run, and an end user has no reason to see either."""
    response = client_for(world["user_a"], world["alpha"]).get("/api/v1/usage/summary/")
    assert response.status_code == 403


def test_usage_series_returns_daily_buckets(world):
    response = client_for(world["admin_a"], world["alpha"]).get("/api/v1/usage/series/")

    assert response.status_code == 200
    assert len(response.data["series"]) == 1
    assert response.data["series"][0]["cost_usd"] == "1.500000"


def test_the_window_parameter_is_clamped_rather_than_rejected(world):
    """A dashboard that 500s on a stray query string is worse than one that
    falls back to a sane window."""
    response = client_for(world["admin_a"], world["alpha"]).get("/api/v1/usage/summary/?days=-9")
    assert response.status_code == 200


# ---------------------------------------------- model names (D-136) ----------


def test_a_workspace_is_never_told_which_model_served_it(world):
    """Model identifiers name the vendor as plainly as a logo would.

    Phase 7A returned `unpriced_models: ["gemini-flash-latest", ...]` to any
    workspace administrator. This is the regression test for that leak.
    """
    response = client_for(world["admin_a"], world["alpha"]).get("/api/v1/usage/summary/")

    assert response.status_code == 200
    body = json.dumps(response.data).lower()

    for vendor in ("gemini", "google", "deepseek", "openai", "groq", "anthropic", "claude"):
        assert vendor not in body, f"the workspace usage payload leaked {vendor!r}"
    assert "unpriced_models" not in response.data["totals"]


def test_a_workspace_still_learns_that_something_is_unpriced(world):
    """The count survives even though the names do not - it tells a tenant
    whether to trust its own cost figure."""
    response = client_for(world["admin_a"], world["alpha"]).get("/api/v1/usage/summary/")
    assert response.data["totals"]["unpriced_model_count"] >= 1


def test_the_tenant_by_model_endpoint_no_longer_exists(world):
    """It was the other half of the same leak."""
    response = client_for(world["admin_a"], world["alpha"]).get("/api/v1/usage/by-model/")
    assert response.status_code == 404


def test_the_workspace_sees_its_usage_by_role_instead(world):
    """A tenant is buying "text reasoning" and "vision", not a named model."""
    response = client_for(world["admin_a"], world["alpha"]).get("/api/v1/usage/summary/")

    engines = {row["engine"] for row in response.data["by_engine"]}
    assert engines <= {"TEXT", "VISION"}
    assert engines, "the breakdown by role must still be there"


def test_the_platform_owner_does_get_model_names(world):
    """The one surface where they belong - an operator setting rates has to
    know what to price."""
    response = client_for(world["owner"]).get("/api/v1/platform/usage/")

    assert response.status_code == 200
    assert "unpriced_models" in response.data["totals"]
