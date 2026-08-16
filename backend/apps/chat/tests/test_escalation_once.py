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


# ------------------------------------------------- reaching the user back ----


def test_the_ticket_carries_the_users_email_address(world):
    """The helpdesk showed "REPORTED BY Rizwan" and nothing else, so the
    engineer had a name and no way to contact anyone (D-166)."""
    escalate(world)
    body = outbox()[0].body

    assert "rizwan@alpha.test" in body
    assert "REPLY TO" in body


def test_reply_to_is_the_user_not_the_workspace_mailbox(world):
    escalate(world)

    assert outbox()[0].reply_to == ["rizwan@alpha.test"]


def test_the_sender_name_is_the_person_who_raised_it(world):
    """A helpdesk that files tickets by the From address recorded every
    escalation as raised by MateAssist's own mailbox. The address is unchanged -
    only the display name now names the person, so nothing about SPF moves."""
    # From address only. Setting smtp_host too would make this dial a real
    # server instead of the in-memory backend, which tests DNS rather than the
    # header under examination.
    world["conversation"].tenant.smtp_from_email = "aiassist@alpha.test"
    world["conversation"].tenant.save()

    escalate(world)
    sender = outbox()[0].from_email

    assert "rizwan@alpha.test" in sender or "Rizwan" in sender or "rizwan" in sender.lower()
    # The address itself must not become the user's, or the workspace's mail
    # server would be sending as a domain it has no authority for.
    assert sender.endswith("<aiassist@alpha.test>")


def test_a_user_with_no_name_still_produces_a_usable_ticket(world):
    """display_name falls back to the email, so the ticket is still actionable
    for an account nobody has filled in."""
    escalate(world)
    body = outbox()[0].body

    assert "no address on file" not in body


# --------------------------------------------- screenshots on the email -----


def attach_screenshot(world, *, key, size=1024, monkeypatch_store=None):
    """A user message carrying a screenshot in the conversation."""
    from apps.chat.models import Message
    from apps.chat.models import Role as MessageRole

    tenant = world["conversation"].tenant
    set_db_tenant(tenant.id)
    Message.all_objects.create(
        tenant=tenant,
        conversation=world["conversation"],
        role=MessageRole.USER,
        text="here is the error",
        attachment_key=key,
        attachment_description="A PowerShell error dialog.",
    )
    set_db_tenant(None)
    if monkeypatch_store is not None:
        monkeypatch_store[key] = b"x" * size


@pytest.fixture
def store(monkeypatch):
    """An in-memory object store, so these tests exercise the escalation rather
    than MinIO."""
    from apps.knowledge import storage

    contents = {}
    monkeypatch.setattr(storage, "get", lambda key: contents[key])
    return contents


def test_screenshots_are_attached_to_the_escalation(world, store):
    """The engineer sees the error dialog, not only a description of it."""
    attach_screenshot(world, key="alpha/1/first.png", monkeypatch_store=store)
    attach_screenshot(world, key="alpha/1/second.png", monkeypatch_store=store)

    escalate(world)
    message = outbox()[0]

    assert [name for name, _, _ in message.attachments] == [
        "screenshot-1.png",
        "screenshot-2.png",
    ]
    assert message.attachments[0][2] == "image/png"


def test_attachments_are_named_without_the_storage_key(world, store):
    """The key carries the tenant id and a UUID, neither of which belongs in a
    helpdesk queue."""
    attach_screenshot(world, key="alpha/1/6f2c-secret-name.png", monkeypatch_store=store)

    escalate(world)

    assert "6f2c-secret-name" not in outbox()[0].attachments[0][0]


def test_the_body_lists_what_was_attached(world, store):
    attach_screenshot(world, key="alpha/1/one.png", size=4096, monkeypatch_store=store)

    escalate(world)

    assert "ATTACHMENTS" in outbox()[0].body
    assert "screenshot-1.png" in outbox()[0].body


def test_oversized_screenshots_are_dropped_and_declared(world, store, settings):
    """Silently dropping one leaves an engineer reading a transcript that
    mentions an image they never received."""
    settings.ESCALATION_ATTACHMENT_BUDGET = 5_000
    attach_screenshot(world, key="alpha/1/small.png", size=1_000, monkeypatch_store=store)
    attach_screenshot(world, key="alpha/1/huge.png", size=90_000, monkeypatch_store=store)

    escalate(world)
    message = outbox()[0]

    assert len(message.attachments) == 1
    assert "not attached" in message.body


def test_the_oldest_screenshot_survives_the_budget(world, store, settings):
    """The first image is usually the error that started the conversation."""
    settings.ESCALATION_ATTACHMENT_BUDGET = 1_500
    attach_screenshot(world, key="alpha/1/first.png", size=1_000, monkeypatch_store=store)
    attach_screenshot(world, key="alpha/1/later.png", size=1_000, monkeypatch_store=store)

    escalate(world)

    assert len(outbox()[0].attachments) == 1
    assert outbox()[0].attachments[0][1] == b"x" * 1_000


def test_an_unreadable_screenshot_does_not_lose_the_escalation(world, store):
    """The user's problem reaching a human matters more than the picture."""
    attach_screenshot(world, key="alpha/1/missing.png")  # never put in the store

    response = escalate(world)

    assert response.status_code == 200
    assert len(outbox()) == 1
    assert outbox()[0].attachments == []


def test_a_conversation_with_no_screenshots_sends_a_clean_email(world):
    escalate(world)

    assert outbox()[0].attachments == []
    assert "ATTACHMENTS" not in outbox()[0].body


def test_the_transcription_is_kept_alongside_the_image(world, store):
    """Some helpdesks strip attachments, and text is searchable in a queue
    where an image is not."""
    attach_screenshot(world, key="alpha/1/one.png", monkeypatch_store=store)

    escalate(world)

    assert "A PowerShell error dialog." in outbox()[0].body
