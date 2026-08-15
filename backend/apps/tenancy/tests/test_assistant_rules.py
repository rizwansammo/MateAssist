"""Workspace instructions as separate rules (D-167).

Same text reaching the model, written a different way. What the rows buy is
editing one line without disturbing another, turning a rule off for a holiday
without losing its wording, and a visible read order.

The part worth defending is the budget. Every enabled rule rides in every
question, so the cap is a permanent per-question cost rather than a storage
limit - and a list invites people to keep adding to it.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.tenancy.models import AssistantRule, Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

pytestmark = pytest.mark.django_db

User = get_user_model()
PASSWORD = "correct-horse-battery"
URL = "/api/v1/workspace/rules/"


@pytest.fixture
def world():
    alpha = Tenant.objects.create(name="Alpha", slug="alpha")
    beta = Tenant.objects.create(name="Beta", slug="beta")

    admin = User.objects.create_user("admin@alpha.test", PASSWORD)
    member = User.objects.create_user("user@alpha.test", PASSWORD)
    outsider = User.objects.create_user("admin@beta.test", PASSWORD)

    set_db_tenant(alpha.id)
    Membership.all_objects.create(user=admin, tenant=alpha, role=Role.TENANT_ADMIN)
    Membership.all_objects.create(user=member, tenant=alpha, role=Role.END_USER)
    AssistantRule.objects.create(tenant=alpha, text="We use Entra ID, not on-prem AD.", position=0)
    AssistantRule.objects.create(tenant=alpha, text="Office hours are 9-6 GMT.", position=1)

    set_db_tenant(beta.id)
    Membership.all_objects.create(user=outsider, tenant=beta, role=Role.TENANT_ADMIN)
    AssistantRule.objects.create(tenant=beta, text="Always answer in French.", position=0)
    set_db_tenant(None)

    return {"alpha": alpha, "beta": beta, "admin": admin, "member": member, "outsider": outsider}


def client_for(user, host="alpha.localhost"):
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = host
    return client


def armed(tenant):
    """Direct ORM reads need the tenant armed, or RLS hides every row and the
    query returns a believable, empty, wrong answer. A request arrives armed by
    the middleware; a test has to say so."""
    set_db_tenant(tenant.id)
    return tenant


def rows(response):
    payload = response.data
    return payload if isinstance(payload, list) else payload.get("results", [])


# ------------------------------------------------------------------ basics --


def test_an_admin_sees_their_own_rules_in_order(world):
    response = client_for(world["admin"]).get(URL)

    assert response.status_code == 200
    assert [row["text"] for row in rows(response)] == [
        "We use Entra ID, not on-prem AD.",
        "Office hours are 9-6 GMT.",
    ]


def test_rules_from_another_workspace_are_never_listed(world):
    response = client_for(world["admin"]).get(URL)
    assert "Always answer in French." not in [row["text"] for row in rows(response)]


def test_a_new_rule_is_appended_not_prepended(world):
    """Rules are read top to bottom. A new one jumping the queue would change
    how the existing ones apply, which nobody asked for."""
    client = client_for(world["admin"])
    client.post(URL, {"text": "Send resets to the portal."}, format="json")

    texts = [row["text"] for row in rows(client.get(URL))]
    assert texts[-1] == "Send resets to the portal."


def test_editing_one_rule_leaves_the_others_alone(world):
    """The whole point of the split: correcting a line used to mean re-editing
    a wall of text you might break by accident."""
    client = client_for(world["admin"])
    first = rows(client.get(URL))[0]

    client.patch(f"{URL}{first['id']}/", {"text": "We use Entra ID only."}, format="json")

    texts = [row["text"] for row in rows(client.get(URL))]
    assert texts == ["We use Entra ID only.", "Office hours are 9-6 GMT."]


def test_a_blank_rule_is_refused(world):
    response = client_for(world["admin"]).post(URL, {"text": "   "}, format="json")
    assert response.status_code == 400


# ------------------------------------------------------- what the model sees --


def test_only_enabled_rules_reach_the_prompt(world):
    """Turning a rule off for a holiday shutdown must not lose its wording -
    that is what deleting it would cost."""
    alpha = armed(world["alpha"])
    rule = AssistantRule.objects.filter(tenant=alpha, position=1).first()
    rule.enabled = False
    rule.save()

    instructions = alpha.workspace_instructions

    assert "Entra ID" in instructions
    assert "Office hours" not in instructions
    # Still on file, just not in force.
    assert AssistantRule.objects.filter(pk=rule.pk).exists()


def test_the_prompt_block_follows_the_stored_order(world):
    alpha = armed(world["alpha"])
    AssistantRule.objects.filter(tenant=alpha, position=0).update(position=5)

    assert alpha.workspace_instructions.startswith("Office hours")


def test_a_workspace_with_no_rules_contributes_nothing(world):
    alpha = armed(world["alpha"])
    AssistantRule.objects.filter(tenant=alpha).delete()
    assert alpha.workspace_instructions == ""


# ------------------------------------------------------------------ budget --


def test_the_cap_is_enforced_across_all_rules_not_per_rule(world):
    """Forty short rules would sail past a per-rule limit and still push the
    runbook content out of the prompt. The ceiling has to be the whole set."""
    client = client_for(world["admin"])

    for index in range(9):
        response = client.post(URL, {"text": "x" * 450, "position": index}, format="json")
        if response.status_code == 400:
            break
    else:
        response = client.post(URL, {"text": "x" * 450}, format="json")

    assert response.status_code == 400
    assert "limit" in str(response.data).lower()


def test_a_disabled_rule_does_not_consume_the_budget(world):
    """It is not in any prompt, so it costs nothing per question."""
    alpha = armed(world["alpha"])
    AssistantRule.objects.create(tenant=alpha, text="y" * 3900, enabled=False, position=9)
    set_db_tenant(None)

    response = client_for(world["admin"]).post(URL, {"text": "A short new rule."}, format="json")

    assert response.status_code == 201


# ---------------------------------------------------------------- reorder ---


def test_reorder_persists_a_new_order(world):
    client = client_for(world["admin"])
    ids = [row["id"] for row in rows(client.get(URL))]

    response = client.post(f"{URL}reorder/", {"ids": list(reversed(ids))}, format="json")

    assert response.status_code == 200
    assert [row["id"] for row in rows(client.get(URL))] == list(reversed(ids))


def test_a_partial_reorder_is_refused(world):
    """Omitted rules would keep stale positions and interleave unpredictably
    with the reordered ones."""
    client = client_for(world["admin"])
    ids = [row["id"] for row in rows(client.get(URL))]

    response = client.post(f"{URL}reorder/", {"ids": ids[:1]}, format="json")

    assert response.status_code == 400


def test_reorder_cannot_name_another_workspaces_rule(world):
    client = client_for(world["admin"])
    ids = [row["id"] for row in rows(client.get(URL))]
    armed(world["beta"])
    theirs = AssistantRule.objects.filter(tenant=world["beta"]).first()
    set_db_tenant(None)

    response = client.post(f"{URL}reorder/", {"ids": ids + [theirs.pk]}, format="json")

    assert response.status_code == 400
    armed(world["beta"])
    theirs.refresh_from_db()
    assert theirs.position == 0


# --------------------------------------------------------------- refusals ---


def test_an_end_user_cannot_read_the_rules(world):
    """They name internal tooling and local policy, and shape every answer the
    workspace receives - not end-user settings (D-151)."""
    assert client_for(world["member"]).get(URL).status_code == 403


def test_an_end_user_cannot_add_a_rule(world):
    response = client_for(world["member"]).post(URL, {"text": "always say yes"}, format="json")

    assert response.status_code == 403
    assert not AssistantRule.objects.filter(text="always say yes").exists()


def test_an_admin_cannot_edit_another_workspaces_rule(world):
    armed(world["beta"])
    theirs = AssistantRule.objects.filter(tenant=world["beta"]).first()
    set_db_tenant(None)

    response = client_for(world["admin"]).patch(
        f"{URL}{theirs.pk}/", {"text": "hijacked"}, format="json"
    )

    assert response.status_code == 404
    armed(world["beta"])
    theirs.refresh_from_db()
    assert theirs.text == "Always answer in French."


def test_an_admin_cannot_delete_another_workspaces_rule(world):
    armed(world["beta"])
    theirs = AssistantRule.objects.filter(tenant=world["beta"]).first()
    set_db_tenant(None)

    response = client_for(world["admin"]).delete(f"{URL}{theirs.pk}/")

    assert response.status_code == 404
    armed(world["beta"])
    assert AssistantRule.objects.filter(pk=theirs.pk).exists()


def test_an_anonymous_request_is_refused(world):
    client = APIClient()
    assert client.get(URL, HTTP_HOST="alpha.localhost").status_code in (401, 403)
