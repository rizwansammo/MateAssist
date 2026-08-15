"""Editing a provider key in place, and probing it live (D-155).

Two things needed proving. That an operator can correct a retired model id
without re-entering the credential - the gap that made a withdrawn
`gemini-1.5-flash` unfixable except by deleting the key. And that this new write
path cannot become a way to change, read, or destroy the credential itself.

The second is the reason the tests exist. A convenience route into the vault is
still a route into the vault.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.ai.models import Engine, Provider, ProviderKey
from apps.tenancy.models import Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

# `default` only, deliberately. These edits record a platform-scope audit event,
# which goes through the `admin` alias - a genuinely separate superuser
# connection that cannot see rows from this test's uncommitted transaction.
# record() already swallows its own failures by design, so the audit write is a
# no-op here and the assertions below are unaffected. Making it real would need
# transaction=True on every test to buy coverage the Phase 7A audit suite
# already provides.
pytestmark = pytest.mark.django_db

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"
ADMIN_HOST = "admin.localhost"
TENANT_HOST = "alpha.localhost"
KEYS_URL = "/api/v1/platform/keys/"

SECRET = "sk-original-credential-value"


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


@pytest.fixture
def vision_key():
    key = ProviderKey(
        engine=Engine.VISION,
        provider=Provider.GEMINI,
        model="gemini-1.5-flash",  # the retired id that started this
        label="primary",
    )
    key.set_secret(SECRET)
    key.save()
    return key


def auth(email, host=ADMIN_HOST):
    response = APIClient().post(
        reverse("accounts:login"),
        {"email": email, "password": PASSWORD},
        format="json",
        HTTP_HOST=host,
    )
    assert response.status_code == 200, response.json()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['access']}")
    return client


def patch_key(client, key, payload, host=ADMIN_HOST):
    return client.patch(f"{KEYS_URL}{key.pk}/", payload, format="json", HTTP_HOST=host)


# ----------------------------------------------------------------- editing --


def test_owner_can_correct_a_retired_model_id(owner, vision_key):
    """The whole point: fix the model without touching the credential."""
    client = auth("owner@platform.test")
    response = patch_key(client, vision_key, {"model": "gemini-2.5-flash-lite"})

    assert response.status_code == 200, response.json()
    vision_key.refresh_from_db()
    assert vision_key.model == "gemini-2.5-flash-lite"


def test_editing_the_model_leaves_the_credential_untouched(owner, vision_key):
    """The security claim. An edit route beside a vault must not be able to
    disturb what the vault holds, or a routine correction becomes a way to
    silently swap in someone else's key."""
    before = vision_key.ciphertext
    client = auth("owner@platform.test")
    patch_key(client, vision_key, {"model": "gemini-2.5-flash", "weight": 5})

    vision_key.refresh_from_db()
    # Byte-identical, not merely still-decryptable: nothing on this path has any
    # business rewriting the sealed value. (A rename is the one exception, and
    # it re-seals deliberately - see the test below.)
    assert vision_key.ciphertext == before
    assert vision_key.reveal() == SECRET
    assert vision_key.last4 == "alue"


def test_renaming_a_key_keeps_its_credential_readable(owner, vision_key):
    """The label is part of the vault's authenticated context, so a rename must
    re-seal. Without it the ciphertext survives but can never be opened again -
    and nothing would notice until the next real provider call."""
    client = auth("owner@platform.test")
    response = patch_key(client, vision_key, {"label": "renamed"})

    assert response.status_code == 200
    vision_key.refresh_from_db()
    assert vision_key.label == "renamed"
    assert vision_key.reveal() == SECRET


def test_a_secret_in_the_payload_is_ignored(owner, vision_key):
    """Not merely undocumented - inert. Someone will try it, and it must not
    half-work: writing a new secret without updating last4 would leave the row
    describing a credential it no longer holds."""
    client = auth("owner@platform.test")
    response = patch_key(
        client, vision_key, {"model": "gemini-2.5-flash", "secret": "sk-attacker-supplied"}
    )

    assert response.status_code == 200
    vision_key.refresh_from_db()
    assert vision_key.reveal() == SECRET


def test_the_role_cannot_be_changed(owner, vision_key):
    """A key's engine is fixed at creation. If a vision credential could become
    the text engine, the contract that text engines never receive images (A-010)
    would depend on an admin form rather than on the type system."""
    client = auth("owner@platform.test")
    patch_key(client, vision_key, {"engine": Engine.TEXT, "model": "gemini-2.5-flash"})

    vision_key.refresh_from_db()
    assert vision_key.engine == Engine.VISION


def test_the_response_never_carries_the_credential(owner, vision_key):
    client = auth("owner@platform.test")
    body = patch_key(client, vision_key, {"model": "gemini-2.5-flash"}).json()

    assert SECRET not in str(body)
    assert "ciphertext" not in body
    assert body["masked"].endswith("alue")


def test_edit_clears_a_rate_limit_but_not_a_revocation(owner, vision_key):
    """A key parked as rate-limited is usually parked because of the setting
    just corrected, so an edit should let it back into the pool. Revocation was
    deliberate, and reviving a retired credential as a side effect of a typo fix
    would be a genuine security failure."""
    vision_key.status = ProviderKey.Status.RATE_LIMITED
    vision_key.save()
    client = auth("owner@platform.test")
    patch_key(client, vision_key, {"model": "gemini-2.5-flash"})
    vision_key.refresh_from_db()
    assert vision_key.status == ProviderKey.Status.ACTIVE

    vision_key.status = ProviderKey.Status.REVOKED
    vision_key.save()
    patch_key(client, vision_key, {"model": "gemini-2.5-flash-lite"})
    vision_key.refresh_from_db()
    assert vision_key.status == ProviderKey.Status.REVOKED


# -------------------------------------------------------------- validation --


def test_switching_to_a_generic_endpoint_requires_a_base_url(owner, vision_key):
    """Validation runs on the RESULT of the edit, not on the fields that
    arrived. `provider` alone would otherwise save cleanly against the existing
    blank base_url and fail on the first real request."""
    client = auth("owner@platform.test")
    response = patch_key(client, vision_key, {"provider": Provider.OPENAI_COMPATIBLE})

    assert response.status_code == 400
    assert "base_url" in response.json()
    vision_key.refresh_from_db()
    assert vision_key.provider == Provider.GEMINI


def test_a_rejected_edit_changes_nothing(owner, vision_key):
    client = auth("owner@platform.test")
    patch_key(client, vision_key, {"provider": Provider.OPENAI_COMPATIBLE, "weight": 50})

    vision_key.refresh_from_db()
    assert vision_key.weight == 1


# ---------------------------------------------------------------- refusals --


def test_an_end_user_cannot_edit_a_key(end_user, vision_key):
    client = auth("user@alpha.test", host=TENANT_HOST)
    response = patch_key(client, vision_key, {"model": "anything"}, host=TENANT_HOST)

    assert response.status_code == 403
    vision_key.refresh_from_db()
    assert vision_key.model == "gemini-1.5-flash"


def test_an_anonymous_request_cannot_edit_a_key(vision_key):
    response = APIClient().patch(
        f"{KEYS_URL}{vision_key.pk}/", {"model": "anything"}, format="json", HTTP_HOST=ADMIN_HOST
    )
    assert response.status_code in (401, 403)


# ------------------------------------------------------------ live probing --


def test_check_reports_a_broken_model_without_failing_the_request(owner, vision_key, monkeypatch):
    """A working endpoint correctly reporting a broken configuration is not
    itself an error. Returning 500 here would be indistinguishable from the
    admin API being down."""
    from apps.ai import probe

    monkeypatch.setattr(
        probe,
        "build_engine",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("404 {'message': 'model not found'}")),
    )

    client = auth("owner@platform.test")
    response = client.post(f"{KEYS_URL}{vision_key.pk}/check/", HTTP_HOST=ADMIN_HOST)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    # The provider's own words, trimmed to the actionable part.
    assert body["detail"] == "model not found"


def test_check_reports_success(owner, vision_key, monkeypatch):
    from apps.ai import probe

    class Fake:
        def describe(self, *a, **k):
            return "described"

    monkeypatch.setattr(probe, "build_engine", lambda *a, **k: Fake())

    client = auth("owner@platform.test")
    body = client.post(f"{KEYS_URL}{vision_key.pk}/check/", HTTP_HOST=ADMIN_HOST).json()

    assert body["ok"] is True
    assert body["model"] == "gemini-1.5-flash"


def test_check_probes_vision_with_an_image_and_text_with_a_message(owner, vision_key, monkeypatch):
    """The probe must exercise the SAME path the real workload uses. A text
    prompt sent to the vision engine would pass while proving nothing about
    whether the model can actually read a screenshot."""
    from apps.ai import probe

    seen = {}

    class Fake:
        def describe(self, image_bytes, *, mime_type, purpose="runbook"):
            seen["image"] = image_bytes
            seen["mime"] = mime_type
            return "ok"

    monkeypatch.setattr(probe, "build_engine", lambda *a, **k: Fake())
    auth("owner@platform.test").post(f"{KEYS_URL}{vision_key.pk}/check/", HTTP_HOST=ADMIN_HOST)

    assert seen["mime"] == "image/png"
    assert seen["image"].startswith(b"\x89PNG")


def test_an_end_user_cannot_probe_a_key(end_user, vision_key):
    """The probe spends the platform's credential. Anyone who could call it
    could burn quota on a key they are not allowed to see."""
    client = auth("user@alpha.test", host=TENANT_HOST)
    response = client.post(f"{KEYS_URL}{vision_key.pk}/check/", HTTP_HOST=TENANT_HOST)
    assert response.status_code == 403
