"""Credential vault - AES-256-GCM envelope encryption (D-071).

Envelope rather than encrypting directly under the KEK: every secret gets its own
random data key, and only that short data key is wrapped by the KEK. Rotating the
KEK then means unwrapping and rewrapping a handful of 32-byte keys instead of
re-encrypting every credential, and a single compromised ciphertext does not
weaken the others.

There is deliberately no "decrypt for display" helper. The only consumer of
decrypt() is the engine client that is about to make a provider call
(D-072) - if you find yourself wanting the plaintext anywhere else, that is the
design telling you something.
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

VERSION = b"\x01"
NONCE_BYTES = 12
DEK_BYTES = 32  # AES-256
KEK_BYTES = 32


class VaultError(Exception):
    """Raised when a secret cannot be sealed or opened."""


def _kek() -> bytes:
    raw = settings.MATEASSIST_VAULT_KEY
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:  # noqa: BLE001 - any decode failure is fatal config
        raise VaultError("MATEASSIST_VAULT_KEY is not valid base64") from exc
    if len(key) != KEK_BYTES:
        raise VaultError(f"MATEASSIST_VAULT_KEY must decode to {KEK_BYTES} bytes, got {len(key)}")
    return key


def _aad(context: str) -> bytes:
    """Additional authenticated data.

    Binds a ciphertext to the row it belongs to, so a blob copied from one
    ProviderKey into another fails to open rather than silently decrypting into
    the wrong engine's credential.
    """
    return context.encode("utf-8")


def seal(plaintext: str, *, context: str) -> str:
    if not plaintext:
        raise VaultError("Refusing to seal an empty secret.")

    dek = os.urandom(DEK_BYTES)
    dek_nonce = os.urandom(NONCE_BYTES)
    kek_nonce = os.urandom(NONCE_BYTES)
    aad = _aad(context)

    ciphertext = AESGCM(dek).encrypt(dek_nonce, plaintext.encode("utf-8"), aad)
    wrapped_dek = AESGCM(_kek()).encrypt(kek_nonce, dek, aad)

    blob = (
        VERSION
        + kek_nonce
        + len(wrapped_dek).to_bytes(2, "big")
        + wrapped_dek
        + dek_nonce
        + ciphertext
    )
    return base64.b64encode(blob).decode("ascii")


def open_sealed(blob: str, *, context: str) -> str:
    try:
        raw = base64.b64decode(blob, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise VaultError("Sealed blob is not valid base64") from exc

    if not raw.startswith(VERSION):
        raise VaultError("Unsupported vault blob version")

    aad = _aad(context)
    cursor = len(VERSION)
    kek_nonce = raw[cursor : cursor + NONCE_BYTES]
    cursor += NONCE_BYTES
    wrapped_len = int.from_bytes(raw[cursor : cursor + 2], "big")
    cursor += 2
    wrapped_dek = raw[cursor : cursor + wrapped_len]
    cursor += wrapped_len
    dek_nonce = raw[cursor : cursor + NONCE_BYTES]
    cursor += NONCE_BYTES
    ciphertext = raw[cursor:]

    try:
        dek = AESGCM(_kek()).decrypt(kek_nonce, wrapped_dek, aad)
        return AESGCM(dek).decrypt(dek_nonce, ciphertext, aad).decode("utf-8")
    except InvalidTag as exc:
        # Wrong KEK, wrong context, or tampered ciphertext - indistinguishable
        # on purpose, and all equally fatal.
        raise VaultError("Sealed secret failed authentication") from exc


def last4(secret: str) -> str:
    """The only part of a credential that is ever stored in the clear."""
    return secret.strip()[-4:]
