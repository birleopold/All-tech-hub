from __future__ import annotations

import json
import re
from collections.abc import Mapping
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from django.conf import settings
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

_WHITESPACE = re.compile(r"\s+")


def public_base_url() -> str:
    """Return the single configured public origin used by canonical SEO signals."""

    configured = (getattr(settings, "PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    if not configured:
        return "https://leosoftug.com"
    parsed = urlsplit(configured)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "https://leosoftug.com"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def public_url(path_or_url: str = "/", query: Mapping[str, object] | None = None) -> str:
    """Build an absolute public URL without inheriting request host or tracking data."""

    value = (path_or_url or "/").strip()
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        path = parsed.path or "/"
    else:
        path = value if value.startswith("/") else f"/{value}"

    absolute = urljoin(f"{public_base_url()}/", path.lstrip("/"))
    if query:
        encoded = urlencode(
            [(key, str(value)) for key, value in query.items() if value not in {None, ""}]
        )
        if encoded:
            absolute = f"{absolute}?{encoded}"
    return absolute


def clean_text(value: object) -> str:
    return _WHITESPACE.sub(" ", strip_tags(str(value or ""))).strip()


def meta_description(value: object, *, fallback: str = "", limit: int = 160) -> str:
    text = clean_text(value) or clean_text(fallback)
    if len(text) <= limit:
        return text
    shortened = text[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return f"{shortened}…"


def meta_title(value: object, *, fallback: str = "", limit: int = 65) -> str:
    text = clean_text(value) or clean_text(fallback)
    if len(text) <= limit:
        return text
    shortened = text[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return shortened or text[:limit]


def script_safe_json(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return mark_safe(
        encoded.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    )


def og_locale(language: str = "en", country: str = "UG") -> str:
    language = clean_text(language).lower().split("-")[0] or "en"
    country = clean_text(country).upper() or "UG"
    return f"{language}_{country}"


def html_language(language: str = "en", country: str = "UG") -> str:
    language = clean_text(language).lower().split("-")[0] or "en"
    country = clean_text(country).upper() or "UG"
    return f"{language}-{country}"
