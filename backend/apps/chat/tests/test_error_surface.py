"""What the chat endpoints return when the engine fails (D-135).

Tested at the HTTP boundary rather than on the mapping function alone, because
the leak was never in the mapping - it was in a view passing `str(exc)` straight
into a response. The mapping can be perfect and the endpoint still leak.
"""

import json
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.ai.engines import NoKeyAvailable, RateLimited
from apps.metering.budgets import BudgetExceeded
from apps.tenancy.models import Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

pytestmark = pytest.mark.django_db(databases=["default", "admin"])

User = get_user_model()

REAL_429 = (
    "Error code: 429 - [{'error': {'code': 429, 'message': 'You exceeded your "
    "current quota, please check your plan and billing details. For more "
    "information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits."
)

VENDORS = ("gemini", "google", "deepseek", "openai", "groq", "anthropic", "claude")


@pytest.fixture
def caller():
    tenant = Tenant.objects.create(name="Netswitch", slug="netswitch")
    user = User.objects.create_user("rizwan@netswitch.test", "correct-horse-battery")
    set_db_tenant(tenant.id)
    Membership.all_objects.create(user=user, tenant=tenant, role=Role.END_USER)

    from apps.chat.models import Conversation

    conversation = Conversation.all_objects.create(tenant=tenant, user=user, title="Broken VPN")
    set_db_tenant(None)

    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = "netswitch.localhost"
    return client, conversation


def assert_no_leak(payload: str) -> None:
    lowered = payload.lower()
    for vendor in VENDORS:
        assert vendor not in lowered, f"response leaked the vendor {vendor!r}: {payload}"
    for fragment in ("429", "quota", "http", "{'error'"):
        assert fragment not in lowered, f"response leaked provider detail {fragment!r}"


# ------------------------------------------------------------ /send/ ---------


def test_send_returns_the_busy_sentence_not_the_providers_error(caller):
    client, conversation = caller

    with patch("apps.ai.router.call_text", side_effect=RateLimited(REAL_429)):
        response = client.post(
            f"/api/v1/chat/conversations/{conversation.pk}/send/", {"text": "hi"}
        )

    assert response.status_code == 429, "a client should know to back off"
    assert response.data["detail"] == (
        "MateAssist is handling a lot of requests right now. Please try again in a moment."
    )
    assert_no_leak(json.dumps(response.data))


def test_send_reports_an_unconfigured_pool_differently(caller):
    """Retrying will not fix a missing key, so it must not say "try again"."""
    client, conversation = caller

    with patch("apps.ai.router.call_text", side_effect=NoKeyAvailable("No usable TEXT key")):
        response = client.post(
            f"/api/v1/chat/conversations/{conversation.pk}/send/", {"text": "hi"}
        )

    assert response.status_code == 503
    assert "can't reach the assistant" in response.data["detail"]
    assert_no_leak(json.dumps(response.data))


def test_an_enforced_budget_explains_itself_instead_of_500ing(caller):
    """BudgetExceeded is not an EngineError, so it escaped both handlers and
    returned a 500 - an enforced cap crashed the chat rather than explaining it."""
    client, conversation = caller
    tenant = conversation.tenant

    exc = BudgetExceeded(tenant=tenant, spent=Decimal("10"), cap=Decimal("5"))
    with patch("apps.ai.router.call_text", side_effect=exc):
        response = client.post(
            f"/api/v1/chat/conversations/{conversation.pk}/send/", {"text": "hi"}
        )

    assert response.status_code == 402
    assert "monthly usage limit" in response.data["detail"]
    assert "administrator" in response.data["detail"]
    assert_no_leak(json.dumps(response.data))


# ---------------------------------------------------------- /stream/ ---------


def test_the_streaming_path_is_the_one_that_leaked(caller):
    """This is the exact path that put a raw Gemini 429 - vendor, quota, docs
    URL and Python dict formatting - into a helpdesk user's chat window."""
    client, conversation = caller

    with patch("apps.ai.router.acquire", side_effect=RateLimited(REAL_429)):
        response = client.post(
            f"/api/v1/chat/conversations/{conversation.pk}/stream/", {"text": "hi"}
        )
        body = b"".join(response.streaming_content).decode()

    assert "event: error" in body
    assert "handling a lot of requests" in body
    assert_no_leak(body)
