"""Credential vault (D-070 to D-074)."""

import base64
import os

import pytest
from django.test import override_settings

from apps.ai import vault
from apps.ai.models import Engine, ProviderKey

SECRET = "sk-deepseek-abcdefghijklmnop9f2a"


def test_round_trip():
    sealed = vault.seal(SECRET, context="providerkey:TEXT:primary")
    assert vault.open_sealed(sealed, context="providerkey:TEXT:primary") == SECRET


def test_ciphertext_does_not_contain_the_plaintext():
    sealed = vault.seal(SECRET, context="ctx")
    assert SECRET not in sealed
    assert SECRET not in base64.b64decode(sealed).decode("latin-1")


def test_same_secret_seals_differently_each_time():
    """Fresh DEK and nonce per seal, so identical credentials do not produce
    identical ciphertext - otherwise the store leaks which keys are duplicates."""
    assert vault.seal(SECRET, context="ctx") != vault.seal(SECRET, context="ctx")


def test_wrong_context_fails_to_open():
    """AAD binds a ciphertext to its row: a blob copied from one key into
    another must fail rather than decrypt as the wrong engine's credential."""
    sealed = vault.seal(SECRET, context="providerkey:TEXT:primary")
    with pytest.raises(vault.VaultError, match="failed authentication"):
        vault.open_sealed(sealed, context="providerkey:VISION:primary")


def test_tampered_ciphertext_is_detected():
    sealed = vault.seal(SECRET, context="ctx")
    raw = bytearray(base64.b64decode(sealed))
    raw[-1] ^= 0xFF
    with pytest.raises(vault.VaultError, match="failed authentication"):
        vault.open_sealed(base64.b64encode(raw).decode(), context="ctx")


def test_rotated_kek_cannot_open_old_secrets():
    """Documents the operational consequence recorded in D-071: losing or
    rotating MATEASSIST_VAULT_KEY orphans every stored credential."""
    sealed = vault.seal(SECRET, context="ctx")
    other_kek = base64.b64encode(os.urandom(32)).decode()

    with (
        override_settings(MATEASSIST_VAULT_KEY=other_kek),
        pytest.raises(vault.VaultError, match="failed authentication"),
    ):
        vault.open_sealed(sealed, context="ctx")


def test_malformed_kek_is_rejected_loudly():
    with (
        override_settings(MATEASSIST_VAULT_KEY=base64.b64encode(os.urandom(16)).decode()),
        pytest.raises(vault.VaultError, match="must decode to 32 bytes"),
    ):
        vault.seal(SECRET, context="ctx")


def test_empty_secret_is_refused():
    with pytest.raises(vault.VaultError, match="empty secret"):
        vault.seal("", context="ctx")


# ------------------------------------------------------------- the model ----


@pytest.mark.django_db
def test_provider_key_stores_only_ciphertext_and_last4():
    key = ProviderKey(engine=Engine.TEXT, label="primary")
    key.set_secret(SECRET)
    key.save()

    key.refresh_from_db()
    assert key.last4 == SECRET[-4:]
    assert SECRET not in key.ciphertext
    assert key.reveal() == SECRET
    assert key.masked.endswith(SECRET[-4:])
    assert SECRET[:-4] not in key.masked


@pytest.mark.django_db
def test_no_serializer_field_exposes_the_plaintext():
    """D-072: write-only is the absence of a read path, not a flag. If a
    ciphertext or secret field ever appears on the read serializer, this fails.
    """
    from apps.platformadmin.serializers import ProviderKeySerializer

    exposed = set(ProviderKeySerializer().fields)
    forbidden = {"ciphertext", "secret", "api_key", "plaintext", "value"}

    assert not (exposed & forbidden), f"vault serializer exposes {exposed & forbidden}"
