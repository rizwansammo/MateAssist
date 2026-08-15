"""An escalation is sent once, not once per click (D-163).

Two clicks on "Email my IT team" sent two identical emails, because the button
stayed live after the first and nothing on the server remembered the send. In a
real helpdesk that is a duplicate ticket, and the engineer who picks up the
second one has no way to know it is the same issue.

Hiding the button is not the fix on its own: two clicks a few milliseconds apart
both leave the browser before any state comes back. The guard has to be a single
atomic claim in the database.
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
HOST = "alpha.localhost"

PROPOSAL = {
    "subject": "Adobe portal password reset",
    "summary": "User cannot sign in and the self-service reset did not work.",
    "category": "Access",
}


@pytest.fixture
def world(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    tenant = Tenant.objects.create(name="Alpha", slug="alpha", support_email="helpdesk@alpha.test")
    user = User.objects.create_user("rizwan@alpha.test", PASSWORD)

    set_db_tenant(tenant.id)
    Membership.all_objects.create(user=user, tenant=tenant, role=Role.END_USER)
    conversation = Conversation.all_objects.create(tenant=tenant, user=user, title="Adobe portal")
    Message.all_objects.create(
        tenant=tenant, conversation=conversation, role=MessageRole.USER, text="cannot log in"
    )
    assistant = Message.all_objects.create(
        tenant=tenant,
        conversation=conversation,
        role=MessageRole.ASSISTANT,
        text="I've drafted an escalation.",
        proposed_escalation=PROPOSAL,
    )
    set_db_tenant(None)

    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = HOST

    return {"client": client, "conversation": conversation, "assistant": assistant}


def escalate(world):
    return world["client"].post(
        f"/api/v1/chat/conversations/{world['conversation'].pk}/escalate/", {}, format="json"
    )


def outbox():
    from django.core import mail

    return mail.outbox


# ------------------------------------------------------------- sending once --


def test_the_first_click_sends(world):
    response = escalate(world)

    assert response.status_code == 200
    assert response.data["sent"] is True
    assert len(outbox()) == 1
    assert "Adobe portal password reset" in outbox()[0].subject


def test_a_second_click_sends_nothing(world):
    """The bug, exactly: two clicks produced two emails."""
    escalate(world)
    response = escalate(world)

    assert len(outbox()) == 1
    assert response.status_code == 409
    assert response.data["already_sent"] is True


def test_the_message_records_when_and_where_it_went(world):
    """What the receipt in the UI is rendered from."""
    escalate(world)
    world["assistant"].refresh_from_db()

    assert world["assistant"].escalation_sent_at is not None
    assert world["assistant"].escalation_recipient == "helpdesk@alpha.test"


def test_the_transcript_reports_the_sent_state(world):
    """Without this the card cannot become a receipt after a page reload, and
    the button would come back."""
    escalate(world)
    response = world["client"].get(f"/api/v1/chat/conversations/{world['conversation'].pk}/")

    message = next(m for m in response.data["messages"] if m["id"] == world["assistant"].pk)
    assert message["escalation_sent_at"] is not None
    assert message["escalation_recipient"] == "helpdesk@alpha.test"


# ------------------------------------------------------------------ failure --


def test_a_failed_send_leaves_the_button_usable(world, monkeypatch):
    """A send that fails must release its claim. Staying marked as sent would
    leave the user with no email and no way to try again - worse than either
    failure alone."""
    from apps.chat import escalation as escalation_module

    monkeypatch.setattr(
        escalation_module,
        "resolve_recipient",
        lambda tenant: "",  # no support address configured
    )

    response = escalate(world)

    assert response.status_code == 502
    assert len(outbox()) == 0
    world["assistant"].refresh_from_db()
    assert world["assistant"].escalation_sent_at is None


def test_a_retry_after_a_failure_can_succeed(world, monkeypatch):
    from apps.chat import escalation as escalation_module

    monkeypatch.setattr(escalation_module, "resolve_recipient", lambda tenant: "")
    escalate(world)

    monkeypatch.undo()
    response = escalate(world)

    assert response.status_code == 200
    assert len(outbox()) == 1


# ------------------------------------------------------- a second escalation --


def test_a_new_proposal_gets_its_own_button(world):
    """Raising another request means asking again, which produces a new
    proposal on a new message. A conversation-level flag would have greyed that
    one out too."""
    escalate(world)

    set_db_tenant(world["conversation"].tenant_id)
    second = Message.all_objects.create(
        tenant=world["conversation"].tenant,
        conversation=world["conversation"],
        role=MessageRole.ASSISTANT,
        text="Here is another escalation.",
        proposed_escalation={"subject": "Still locked out", "summary": "No reply yet."},
    )
    set_db_tenant(None)

    response = escalate(world)

    assert response.status_code == 200
    assert len(outbox()) == 2
    second.refresh_from_db()
    assert second.escalation_sent_at is not None
    # The first is untouched - its receipt still shows its own time.
    world["assistant"].refresh_from_db()
    assert world["assistant"].escalation_sent_at is not None
