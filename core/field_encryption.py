"""Small authenticated-encryption helpers for sensitive application fields."""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_ENCRYPTED_PREFIX = "~"
_TOTP_AAD = b"leosoft:staff-totp:v1"
_NONCE_BYTES = 8


def _encryption_key() -> bytes:
    configured = str(getattr(settings, "FIELD_ENCRYPTION_KEY", "") or "")
    if len(configured) < 32:
        raise ImproperlyConfigured(
            "ALLTECH_FIELD_ENCRYPTION_KEY or ALLTECH_SECRET_KEY must be at least 32 characters."
        )
    return hashlib.sha256(configured.encode("utf-8")).digest()


def is_protected_secret(value: str) -> bool:
    return bool(value and value.startswith(_ENCRYPTED_PREFIX))


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
    except (ValueError, TypeError):
        raise ImproperlyConfigured("The stored TOTP secret is not valid base32 data.")

    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(_encryption_key()).encrypt(nonce, raw_secret, _TOTP_AAD)
    encoded = base64.urlsafe_b64encode(nonce + ciphertext).rstrip(b"=").decode("ascii")
    protected = _ENCRYPTED_PREFIX + encoded
    if len(protected) > 64:
        raise ImproperlyConfigured(
            "The encrypted TOTP token exceeds StaffTwoFactor.secret capacity."
        )
    return protected


def reveal_totp_secret(value: str) -> str:
    """Decrypt a protected secret; legacy plaintext base32 remains readable."""

    if not value or not is_protected_secret(value):
        return value
    token = value[len(_ENCRYPTED_PREFIX) :]
    padded = token + ("=" * ((4 - len(token) % 4) % 4))
    try:
        payload = base64.urlsafe_b64decode(padded.encode("ascii"))
        nonce = payload[:_NONCE_BYTES]
        ciphertext = payload[_NONCE_BYTES:]
        raw_secret = AESGCM(_encryption_key()).decrypt(nonce, ciphertext, _TOTP_AAD)
    except (ValueError, InvalidTag, UnicodeError) as exc:
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
