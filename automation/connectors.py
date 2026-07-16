from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

from core.models import CompanySettings


class ConnectorError(Exception):
    def __init__(self, message: str, *, retryable: bool = True, code: str = ""):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


@dataclass(frozen=True)
class MetaConfig:
    enabled: bool
    graph_version: str
    page_id: str
    instagram_account_id: str
    access_token: str
    timeout_seconds: int

    @classmethod
    def load(cls) -> "MetaConfig":
        version = str(getattr(settings, "META_GRAPH_VERSION", "v23.0")).strip()
        if not re.fullmatch(r"v\d+\.\d+", version):
            version = "v23.0"
        return cls(
            enabled=bool(getattr(settings, "META_AUTO_PUBLISH_ENABLED", False)),
            graph_version=version,
            page_id=str(getattr(settings, "META_PAGE_ID", "")).strip(),
            instagram_account_id=str(
                getattr(settings, "META_INSTAGRAM_ACCOUNT_ID", "")
            ).strip(),
            access_token=str(getattr(settings, "META_PAGE_ACCESS_TOKEN", "")).strip(),
            timeout_seconds=max(
                5,
                min(60, int(getattr(settings, "AUTOMATION_HTTP_TIMEOUT_SECONDS", 20))),
            ),
        )

    def supports(self, channel: str) -> bool:
        if not self.enabled or not self.access_token:
            return False
        if channel == "facebook":
            return bool(self.page_id)
        if channel == "instagram":
            return bool(self.instagram_account_id)
        return False


TRANSIENT_META_CODES = {1, 2, 4, 17, 32, 341, 613}


def _meta_url(config: MetaConfig, path: str) -> str:
    return f"https://graph.facebook.com/{config.graph_version}/{path.lstrip('/')}"


def _parse_graph_error(raw: bytes, status: int) -> ConnectorError:
    message = f"Meta API returned HTTP {status}."
    code = ""
    try:
        payload = json.loads(raw.decode("utf-8"))
        error = payload.get("error") or {}
        message = str(error.get("message") or message)
        code = str(error.get("code") or "")
    except Exception:
        pass
    numeric_code = int(code) if code.isdigit() else None
    retryable = status in {408, 409, 425, 429} or status >= 500
    if numeric_code in TRANSIENT_META_CODES:
        retryable = True
    if status in {400, 401, 403, 404} and numeric_code not in TRANSIENT_META_CODES:
        retryable = False
    return ConnectorError(message[:1000], retryable=retryable, code=code)


def _graph_request(
    config: MetaConfig,
    method: str,
    path: str,
    *,
    data: dict | None = None,
    query: dict | None = None,
) -> dict:
    query_data = dict(query or {})
    body_data = dict(data or {})
    if method.upper() == "GET":
        query_data["access_token"] = config.access_token
    else:
        body_data["access_token"] = config.access_token

    url = _meta_url(config, path)
    if query_data:
        url = f"{url}?{urlencode(query_data)}"
    encoded = urlencode(body_data).encode("utf-8") if body_data else None
    request = Request(
        url,
        data=encoded,
        method=method.upper(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "LEOSOFT-Automation/1.0",
        },
    )
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:
            raw = response.read()
    except HTTPError as exc:
        raw = exc.read() if hasattr(exc, "read") else b""
        raise _parse_graph_error(raw, exc.code) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ConnectorError(
            "Meta API could not be reached. The job will retry.",
            retryable=True,
        ) from exc

    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception as exc:
        raise ConnectorError(
            "Meta API returned an unreadable response.",
            retryable=True,
        ) from exc
    if isinstance(payload, dict) and payload.get("error"):
        raise _parse_graph_error(raw, 400)
    return payload if isinstance(payload, dict) else {"data": payload}


def _permalink(config: MetaConfig, object_id: str) -> str:
    if not object_id:
        return ""
    try:
        payload = _graph_request(
            config,
            "GET",
            object_id,
            query={"fields": "permalink_url,permalink"},
        )
        return str(payload.get("permalink_url") or payload.get("permalink") or "")
    except ConnectorError:
        return ""


def channel_is_configured(channel: str) -> bool:
    return MetaConfig.load().supports(channel)


def _destination_url(post) -> str:
    if post.product_id and post.product:
        company = CompanySettings.load()
        base = (company.website or "https://leosoftug.com").rstrip("/")
        return f"{base}{post.product.get_absolute_url()}"
    return ""


def publish_facebook(*, post, image_url: str = "") -> dict:
    config = MetaConfig.load()
    if not config.supports("facebook"):
        raise ConnectorError(
            "Facebook automatic publishing is not configured.",
            retryable=False,
        )
    if image_url:
        payload = _graph_request(
            config,
            "POST",
            f"{config.page_id}/photos",
            data={
                "url": image_url,
                "caption": post.caption,
                "published": "true",
            },
        )
    else:
        data = {"message": post.caption}
        destination = _destination_url(post)
        if destination:
            data["link"] = destination
        payload = _graph_request(
            config,
            "POST",
            f"{config.page_id}/feed",
            data=data,
        )
    external_id = str(payload.get("post_id") or payload.get("id") or "")
    if not external_id:
        raise ConnectorError(
            "Facebook accepted the request but did not return a post identifier.",
            retryable=True,
        )
    return {
        "external_id": external_id,
        "external_url": _permalink(config, external_id),
        "provider": "meta",
    }


def publish_instagram(*, post, image_url: str = "") -> dict:
    config = MetaConfig.load()
    if not config.supports("instagram"):
        raise ConnectorError(
            "Instagram automatic publishing is not configured.",
            retryable=False,
        )
    if not image_url or not image_url.lower().startswith("https://"):
        raise ConnectorError(
            "Instagram automatic publishing requires a public HTTPS image URL.",
            retryable=False,
        )
    container = _graph_request(
        config,
        "POST",
        f"{config.instagram_account_id}/media",
        data={"image_url": image_url, "caption": post.caption},
    )
    creation_id = str(container.get("id") or "")
    if not creation_id:
        raise ConnectorError(
            "Instagram did not return a media container identifier.",
            retryable=True,
        )
    published = _graph_request(
        config,
        "POST",
        f"{config.instagram_account_id}/media_publish",
        data={"creation_id": creation_id},
    )
    external_id = str(published.get("id") or "")
    if not external_id:
        raise ConnectorError(
            "Instagram did not return a published media identifier.",
            retryable=True,
        )
    return {
        "external_id": external_id,
        "external_url": _permalink(config, external_id),
        "provider": "meta",
        "creation_id": creation_id,
    }


def publish_social_post(*, channel: str, post, image_url: str = "") -> dict:
    if channel == "facebook":
        return publish_facebook(post=post, image_url=image_url)
    if channel == "instagram":
        return publish_instagram(post=post, image_url=image_url)
    raise ConnectorError(
        f"{channel.title()} does not have an automatic publisher in LEOSOFT yet.",
        retryable=False,
    )
