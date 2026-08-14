"""Conversation history (D-142).

The threads were never lost - `Conversation` rows have been persisted since
Phase 6. What was missing was any way back to them: the page held the open
thread in component state, so a refresh started a new one and orphaned the old.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.chat.models import Conversation, Message, Role as MessageRole
from apps.tenancy.models import Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def world():
    tenant = Tenant.objects.create(name="Netswitch", slug="netswitch")
    user = User.objects.create_user("rizwan@netswitch.test", "correct-horse-battery")
    other = User.objects.create_user("someone@netswitch.test", "correct-horse-battery")

    set_db_tenant(tenant.id)
    Membership.all_objects.create(user=user, tenant=tenant, role=Role.END_USER)
    Membership.all_objects.create(user=other, tenant=tenant, role=Role.END_USER)

    mine = Conversation.all_objects.create(tenant=tenant, user=user, title="VPN keeps dropping")
    for index in range(3):
        Message.all_objects.create(
            tenant=tenant, conversation=mine, role=MessageRole.USER, text=f"message {index}"
        )
    theirs = Conversation.all_objects.create(tenant=tenant, user=other, title="Printer jammed")
    set_db_tenant(None)

    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = "netswitch.localhost"
    return client, mine, theirs


def rows(response):
    payload = response.data
    return payload if isinstance(payload, list) else payload.get("results", [])


def test_the_list_returns_the_users_own_threads(world):
    client, mine, _theirs = world

    response = client.get("/api/v1/chat/conversations/")

    assert response.status_code == 200
    assert [row["id"] for row in rows(response)] == [mine.pk]


def test_another_users_thread_is_not_listed(world):
    """Same workspace, different person. RLS scopes the tenant; this scopes the
    user, because a colleague's support conversation is not yours to read."""
    client, _mine, theirs = world

    assert theirs.pk not in [row["id"] for row in rows(client.get("/api/v1/chat/conversations/"))]
    assert client.get(f"/api/v1/chat/conversations/{theirs.pk}/").status_code == 404


def test_the_list_does_not_carry_every_message(world):
    """The sidebar loads on every visit. Nesting whole transcripts to render a
    list of titles sends an unbounded payload that grows as the user talks."""
    client, _mine, _theirs = world

    row = rows(client.get("/api/v1/chat/conversations/"))[0]

    assert "messages" not in row
    assert row["message_count"] == 3


def test_opening_one_returns_its_full_transcript(world):
    """The detail endpoint is where the messages live."""
    client, mine, _theirs = world

    response = client.get(f"/api/v1/chat/conversations/{mine.pk}/")

    assert response.status_code == 200
    assert len(response.data["messages"]) == 3


def test_a_thread_can_be_deleted_by_its_owner(world):
    client, mine, _theirs = world

    assert client.delete(f"/api/v1/chat/conversations/{mine.pk}/").status_code == 204
    assert not Conversation.all_objects.filter(pk=mine.pk).exists()


def test_deleting_a_thread_removes_its_messages(world):
    """A "deleted" conversation whose messages quietly persist is the kind of
    thing that surfaces in a data-subject request later."""
    client, mine, _theirs = world

    client.delete(f"/api/v1/chat/conversations/{mine.pk}/")

    assert not Message.all_objects.filter(conversation_id=mine.pk).exists()


def test_you_cannot_delete_someone_elses_thread(world):
    client, _mine, theirs = world

    assert client.delete(f"/api/v1/chat/conversations/{theirs.pk}/").status_code == 404
    assert Conversation.all_objects.filter(pk=theirs.pk).exists()
