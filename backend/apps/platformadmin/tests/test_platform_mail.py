"""Mail sent by MateAssist itself (D-175).

The platform could not send an email at all: `EMAIL_BACKEND` was the console
backend and `EMAIL_HOST` was unset, so anything it "sent" was printed to a log.
Everything that recovers an account depends on this working, so it is
configurable in the console and provable with a test button.

The separation being defended: platform mail must never travel over a tenant's
SMTP connection. Account recovery for the whole platform cannot sit behind
infrastructure a customer controls, or behind their mailbox staying paid for.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.platformadmin import mail as platform_mail
from apps.platformadmin.models import PlatformSettings
from apps.tenancy.models import Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

pytestmark = pytest.mark.django_db

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"
ADMIN_HOST = "admin.localhost"

MAIL_URL = "/api/v1/platform/mail/"
TEST_URL = "/api/v1/platform/mail-test/"
SECRET = "gmail-app-password-value"


@pytest.fixture
def owner():
    set_db_tenant(None)
    user = User.objects.create_user("owner@platform.test", PASSWORD)
    Membership.all_objects.create(user=user, tenant=None, role=Role.PLATFORM_OWNER)
    return user


@pytest.fixture
def end_user():
    tenant = Tenant.objects.create(name="Alpha", slug="alpha")
    user = User.objects.create_user("user@alpha.test", PASSWORD)
    set_db_tenant(tenant.id)
    Membership.all_objects.create(user=user, tenant=tenant, role=Role.END_USER)
    set_db_tenant(None)
    return user


def client_for(user, host=ADMIN_HOST):
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = host
    return client


# ---------------------------------------------------------------- settings --


def test_settings_exist_before_anyone_saves_anything(owner):
    """A fresh deployment must be able to open the page."""
    response = client_for(owner).get(MAIL_URL)

    assert response.status_code == 200
    assert response.data["is_configured"] is False


def test_the_owner_can_save_smtp_settings(owner):
    response = client_for(owner).patch(
        MAIL_URL,
        {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_username": "platform@mateassist.test",
            "smtp_password": SECRET,
            "from_email": "noreply@mateassist.test",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["is_configured"] is True
    assert PlatformSettings.load().reveal_smtp_password() == SECRET


def test_the_password_is_sealed_not_stored_in_the_clear(owner):
    client_for(owner).patch(MAIL_URL, {"smtp_password": SECRET}, format="json")

    config = PlatformSettings.load()
    assert SECRET not in config.smtp_password_ciphertext
    assert config.reveal_smtp_password() == SECRET


def test_the_api_never_returns_the_password(owner):
    client_for(owner).patch(MAIL_URL, {"smtp_password": SECRET}, format="json")

    body = str(client_for(owner).get(MAIL_URL).data)

    assert SECRET not in body
    assert "ciphertext" not in body


def test_omitting_the_password_leaves_it_alone(owner):
    """Saving the From address must not wipe a working credential."""
    client_for(owner).patch(MAIL_URL, {"smtp_password": SECRET}, format="json")
    client_for(owner).patch(MAIL_URL, {"from_email": "new@mateassist.test"}, format="json")

    assert PlatformSettings.load().reveal_smtp_password() == SECRET


def test_an_empty_password_clears_it(owner):
    """The counterpart: there has to be a way to remove a credential."""
    client_for(owner).patch(MAIL_URL, {"smtp_password": SECRET}, format="json")
    client_for(owner).patch(MAIL_URL, {"smtp_password": ""}, format="json")

    assert PlatformSettings.load().reveal_smtp_password() == ""


def test_a_host_without_a_from_address_is_not_configured(owner):
    """Mail from that setup arrives claiming to be from nobody."""
    client_for(owner).patch(MAIL_URL, {"smtp_host": "smtp.gmail.com"}, format="json")

    assert PlatformSettings.load().is_configured is False


# ----------------------------------------------------------------- sending --


def test_the_from_header_carries_the_platform_name(owner):
    client_for(owner).patch(
        MAIL_URL,
        {"from_email": "noreply@mateassist.test", "from_name": "MateAssist"},
        format="json",
    )

    assert platform_mail.from_address() == "MateAssist <noreply@mateassist.test>"


def test_a_name_with_a_comma_is_quoted(owner):
    """Interpolated raw, it would be parsed as two recipients."""
    client_for(owner).patch(
        MAIL_URL,
        {"from_email": "noreply@mateassist.test", "from_name": "MateAssist, Ltd"},
        format="json",
    )

    assert platform_mail.from_address() == '"MateAssist, Ltd" <noreply@mateassist.test>'


def test_the_test_button_sends_to_the_owner(owner, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    from django.core import mail

    response = client_for(owner).post(TEST_URL, {}, format="json")

    assert response.status_code == 200
    assert response.data["sent"] is True
    assert mail.outbox[0].to == ["owner@platform.test"]


def test_a_broken_mail_server_reports_instead_of_crashing(owner, monkeypatch):
    """A working endpoint reporting broken mail is not itself an error, and a
    500 here is indistinguishable from the console being down."""
    monkeypatch.setattr(
        platform_mail,
        "connection",
        lambda: (_ for _ in ()).throw(OSError("Username and Password not accepted")),
    )

    response = client_for(owner).post(TEST_URL, {}, format="json")

    assert response.status_code == 200
    assert response.data["sent"] is False
    # The provider's own words: the reader is debugging their own mail server.
    assert "not accepted" in response.data["detail"]


def test_platform_mail_does_not_use_a_tenants_connection(owner):
    """The separation this module exists for. A reset code routed through a
    customer's SMTP puts platform recovery behind their infrastructure."""
    tenant = Tenant.objects.create(
        name="Alpha",
        slug="alpha",
        smtp_host="smtp.customer.test",
        smtp_from_email="helpdesk@customer.test",
    )
    tenant.set_smtp_password("customer-secret")
    tenant.save()

    client_for(owner).patch(MAIL_URL, {"from_email": "noreply@mateassist.test"}, format="json")

    assert "customer.test" not in platform_mail.from_address()


# ---------------------------------------------------------------- refusals --


def test_an_end_user_cannot_read_the_mail_settings(end_user):
    response = client_for(end_user, host="alpha.localhost").get(MAIL_URL)
    assert response.status_code == 403


def test_an_end_user_cannot_change_the_mail_settings(end_user):
    response = client_for(end_user, host="alpha.localhost").patch(
        MAIL_URL, {"smtp_host": "evil.test"}, format="json"
    )

    assert response.status_code == 403
    assert PlatformSettings.load().smtp_host == ""


def test_an_end_user_cannot_spend_the_platforms_mail_quota(end_user):
    response = client_for(end_user, host="alpha.localhost").post(TEST_URL, {}, format="json")
    assert response.status_code == 403


def test_an_anonymous_request_is_refused():
    client = APIClient()
    client.defaults["HTTP_HOST"] = ADMIN_HOST
    assert client.get(MAIL_URL).status_code in (401, 403)
