"""Serving a message's screenshot back to its sender (D-156).

The portal used to show the vision engine's transcription instead of the image,
because the image had no route out of object storage. Adding one means adding a
way to read a user's screenshot, so these tests are mostly about who cannot.

The endpoint is nested under the conversation on purpose: authorisation is
structural rather than a check someone has to remember to write. Proving that
holds is the point of the file.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.chat.models import Conversation, Message
from apps.chat.models import Role as MessageRole
from apps.tenancy.models import Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

pytestmark = pytest.mark.django_db

User = get_user_model()
PASSWORD = "correct-horse-battery"
PNG = b"\x89PNG\r\n\x1a\nfake-but-recognisable"


@pytest.fixture
def world(monkeypatch):
    """Two workspaces, each with a user who has sent a screenshot."""
    from apps.knowledge import storage

    store = {}
    monkeypatch.setattr(storage, "put", lambda key, data, content_type: store.update({key: data}))
    monkeypatch.setattr(storage, "get", lambda key: store[key])

    alpha = Tenant.objects.create(name="Alpha", slug="alpha")
    beta = Tenant.objects.create(name="Beta", slug="beta")

    alice = User.objects.create_user("alice@alpha.test", PASSWORD)
    bob = User.objects.create_user("bob@alpha.test", PASSWORD)
    mallory = User.objects.create_user("mallory@beta.test", PASSWORD)

    set_db_tenant(alpha.id)
    Membership.all_objects.create(user=alice, tenant=alpha, role=Role.END_USER)
    Membership.all_objects.create(user=bob, tenant=alpha, role=Role.END_USER)
    conversation = Conversation.all_objects.create(tenant=alpha, user=alice, title="Error on boot")
    message = Message.all_objects.create(
        tenant=alpha,
        conversation=conversation,
        role=MessageRole.USER,
        text="what is this?",
        attachment_key="alpha/1/screenshot.png",
        attachment_description="A PowerShell execution policy error.",
    )
    plain = Message.all_objects.create(
        tenant=alpha, conversation=conversation, role=MessageRole.USER, text="no image here"
    )

    set_db_tenant(beta.id)
    Membership.all_objects.create(user=mallory, tenant=beta, role=Role.END_USER)
    set_db_tenant(None)

    store["alpha/1/screenshot.png"] = PNG

    return {
        "conversation": conversation,
        "message": message,
        "plain": plain,
        "alice": alice,
        "bob": bob,
        "mallory": mallory,
        "store": store,
    }


def client_for(user, host="alpha.localhost"):
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = host
    return client


def url(conversation, message):
    return f"/api/v1/chat/conversations/{conversation.pk}/messages/{message.pk}/attachment/"


# ------------------------------------------------------------------ serving --


def test_the_sender_gets_their_own_screenshot_back(world):
    response = client_for(world["alice"]).get(url(world["conversation"], world["message"]))

    assert response.status_code == 200
    assert response.content == PNG
    assert response["Content-Type"] == "image/png"


def test_the_response_is_not_publicly_cacheable(world):
    """A shared cache holding one user's screenshot would hand it to whoever
    asked next."""
    response = client_for(world["alice"]).get(url(world["conversation"], world["message"]))
    assert "private" in response["Cache-Control"]
    assert "public" not in response["Cache-Control"]


def test_a_message_without_an_attachment_is_a_404(world):
    response = client_for(world["alice"]).get(url(world["conversation"], world["plain"]))
    assert response.status_code == 404


def test_a_key_missing_from_storage_is_a_404_not_a_500(world):
    """Storage losing an object must not take the conversation down with it -
    the rest of the transcript is still readable and still worth showing."""
    world["store"].clear()
    response = client_for(world["alice"]).get(url(world["conversation"], world["message"]))
    assert response.status_code == 404


# ---------------------------------------------------------------- refusals ---


def test_another_user_in_the_same_workspace_is_refused(world):
    """A colleague is not an attacker, but a screenshot of an error dialog can
    carry an account name, a ticket, a customer record. The conversation is
    Alice's."""
    response = client_for(world["bob"]).get(url(world["conversation"], world["message"]))
    assert response.status_code == 404
    assert PNG not in response.content


def test_a_user_in_another_workspace_is_refused(world):
    """The headline case. Cross-tenant reads are what the whole isolation model
    exists to prevent, and a new binary endpoint is a new place to get it
    wrong."""
    response = client_for(world["mallory"], host="beta.localhost").get(
        url(world["conversation"], world["message"])
    )
    assert response.status_code in (403, 404)
    assert PNG not in response.content


def test_an_anonymous_request_is_refused(world):
    client = APIClient()
    client.defaults["HTTP_HOST"] = "alpha.localhost"
    response = client.get(url(world["conversation"], world["message"]))
    assert response.status_code in (401, 403)


def test_a_message_id_from_another_conversation_cannot_be_substituted(world):
    """The message is looked up WITHIN the authorised conversation, so pairing a
    conversation you own with a message id you do not must fail. Checking only
    the conversation would make the message id a free parameter."""
    set_db_tenant(world["conversation"].tenant_id)
    other = Conversation.all_objects.create(
        tenant=world["conversation"].tenant, user=world["bob"], title="Bob's thread"
    )
    stolen = Message.all_objects.create(
        tenant=world["conversation"].tenant,
        conversation=other,
        role=MessageRole.USER,
        text="bob's screenshot",
        attachment_key="alpha/1/screenshot.png",
    )
    set_db_tenant(None)

    response = client_for(world["alice"]).get(url(world["conversation"], stolen))
    assert response.status_code == 404


# ------------------------------------------------------------- serializer ----


def test_the_transcript_reports_the_attachment_without_leaking_its_key(world):
    """`has_attachment` drives the UI. The storage path must not travel with it:
    it names the tenant and the object, and a client has no use for either."""
    response = client_for(world["alice"]).get(
        f"/api/v1/chat/conversations/{world['conversation'].pk}/"
    )

    assert response.status_code == 200
    messages = {m["id"]: m for m in response.data["messages"]}
    assert messages[world["message"].pk]["has_attachment"] is True
    assert messages[world["plain"].pk]["has_attachment"] is False
    assert "attachment_key" not in messages[world["message"].pk]
    assert "screenshot.png" not in str(response.data)
