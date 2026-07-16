from __future__ import annotations

import json
import re
import time
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
TRANSIENT_META_PHRASES = (
    "temporarily unavailable",
    "please try again",
    "try again later",
    "not ready",
    "still processing",
    "media id is not available",
    "rate limit",
)


def _meta_url(config: MetaConfig, path: str) -> str:
    return f"https://graph.facebook.com/{config.graph_version}/{path.lstrip('/')}"


def _parse_graph_error(raw: bytes, status: int) -> ConnectorError:
    message = f"Meta API returned HTTP {status}."
    code = ""
    subcode = ""
    try:
        payload = json.loads(raw.decode("utf-8"))
        error = payload.get("error") or {}
        message = str(error.get("message") or message)
        code = str(error.get("code") or "")
        subcode = str(error.get("error_subcode") or "")
    except Exception:
        pass
    numeric_code = int(code) if code.isdigit() else None
    lower_message = message.lower()
    retryable = status in {408, 409, 425, 429} or status >= 500
    if numeric_code in TRANSIENT_META_CODES:
        retryable = True
    if any(phrase in lower_message for phrase in TRANSIENT_META_PHRASES):
        retryable = True
    if (
        status in {400, 401, 403, 404}
        and numeric_code not in TRANSIENT_META_CODES
        and not any(phrase in lower_message for phrase in TRANSIENT_META_PHRASES)
    ):
        retryable = False
    combined_code = f"{code}:{subcode}".strip(":")
    return ConnectorError(
        message[:1000],
        retryable=retryable,
        code=combined_code,
    )


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
            "Meta API could not be reached. The delivery outcome may be unknown; verify the platform before manually requeuing this job.",
            retryable=True,
        ) from exc

    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception as exc:
        raise ConnectorError(
            "Meta API returned an unreadable response. Verify the platform before manually requeuing if the final outcome is uncertain.",
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
            "Facebook accepted the request but did not return a post identifier. Verify the Page before requeuing.",
            retryable=False,
        )
    return {
        "external_id": external_id,
        "external_url": _permalink(config, external_id),
        "provider": "meta",
    }


def _wait_for_instagram_container(config: MetaConfig, creation_id: str) -> None:
    polls = max(
        1,
        min(10, int(getattr(settings, "META_MEDIA_STATUS_POLLS", 5))),
    )
    interval = max(
        1,
        min(5, int(getattr(settings, "META_MEDIA_STATUS_POLL_SECONDS", 2))),
    )
    last_status = ""
    for index in range(polls):
        payload = _graph_request(
            config,
            "GET",
            creation_id,
            query={"fields": "status_code"},
        )
        last_status = str(payload.get("status_code") or "").upper()
        if last_status == "FINISHED":
            return
        if last_status in {"ERROR", "EXPIRED"}:
            raise ConnectorError(
                f"Instagram media preparation ended with status {last_status}.",
                retryable=False,
            )
        if index + 1 < polls:
            time.sleep(interval)
    raise ConnectorError(
        f"Instagram media is still processing ({last_status or 'unknown status'}).",
        retryable=True,
    )


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
    _wait_for_instagram_container(config, creation_id)
    published = _graph_request(
        config,
        "POST",
        f"{config.instagram_account_id}/media_publish",
        data={"creation_id": creation_id},
    )
    external_id = str(published.get("id") or "")
    if not external_id:
        raise ConnectorError(
            "Instagram did not return a published media identifier. Verify the account before requeuing.",
            retryable=False,
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
