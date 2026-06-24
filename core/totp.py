import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def token_for(secret: str, timestamp=None, interval: int = 30) -> str:
    counter = int(timestamp or time.time()) // interval
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def verify_token(secret: str, token: str, timestamp=None, window: int = 1) -> bool:
    token = (token or "").replace(" ", "")
    if not token.isdigit() or len(token) != 6:
        return False
    now = timestamp or time.time()
    return any(
        hmac.compare_digest(token_for(secret, now + step * 30), token)
        for step in range(-window, window + 1)
    )


def provisioning_uri(secret: str, username: str, issuer: str = "ALLTECH Hub") -> str:
    label = quote(f"{issuer}:{username}")
    return (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )
