"""Small authenticated-encryption helpers for sensitive application fields."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_TOTP_AAD = b"leosoft:staff-totp:v1"
_NONCE_BYTES = 12
_PROTECTED_LENGTH = 64
_PROTECTED_PATTERN = re.compile(r"^[A-Za-z0-9_-]{64}$")


def _encryption_key() -> bytes:
    configured = str(getattr(settings, "FIELD_ENCRYPTION_KEY", "") or "")
    if len(configured) < 32:
        raise ImproperlyConfigured(
            "ALLTECH_FIELD_ENCRYPTION_KEY or ALLTECH_SECRET_KEY must be at least 32 characters."
        )
    return hashlib.sha256(configured.encode("utf-8")).digest()


def is_protected_secret(value: str) -> bool:
    """Encrypted tokens are fixed-length URL-safe base64; plaintext TOTP is 32 chars."""

    return bool(value and _PROTECTED_PATTERN.fullmatch(value))


def _decode_base32(value: str) -> bytes:
    cleaned = value.strip().replace(" ", "").upper()
    padded = cleaned + ("=" * ((8 - len(cleaned) % 8) % 8))
    return base64.b32decode(padded, casefold=True)


def protect_totp_secret(secret: str) -> str:
    """Encrypt a base32 TOTP secret in a compact authenticated token."""

    if not secret or is_protected_secret(secret):
        return secret
    try:
        raw_secret = _decode_base32(secret)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise ImproperlyConfigured(
            "The stored TOTP secret is not valid base32 data."
        ) from exc

    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(_encryption_key()).encrypt(nonce, raw_secret, _TOTP_AAD)
    protected = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    if len(protected) != _PROTECTED_LENGTH:
        raise ImproperlyConfigured(
            "The encrypted TOTP token does not match StaffTwoFactor.secret capacity."
        )
    return protected


def reveal_totp_secret(value: str) -> str:
    """Decrypt a protected secret; legacy plaintext base32 remains readable."""

    if not value or not is_protected_secret(value):
        return value
    try:
        payload = base64.urlsafe_b64decode(value.encode("ascii"))
        nonce = payload[:_NONCE_BYTES]
        ciphertext = payload[_NONCE_BYTES:]
        raw_secret = AESGCM(_encryption_key()).decrypt(nonce, ciphertext, _TOTP_AAD)
    except (binascii.Error, ValueError, InvalidTag, UnicodeError) as exc:
        raise ImproperlyConfigured(
            "A staff TOTP secret could not be decrypted. Check the field encryption key."
        ) from exc
    return base64.b32encode(raw_secret).decode("ascii").rstrip("=")


def ensure_profile_secret_protected(profile) -> str:
    """Encrypt a legacy plaintext secret in place and return its clear value."""

    clear_secret = reveal_totp_secret(profile.secret)
    protected = protect_totp_secret(clear_secret)
    if profile.secret != protected:
        profile.secret = protected
        profile.save(update_fields=["secret", "updated_at"])
    return clear_secret
