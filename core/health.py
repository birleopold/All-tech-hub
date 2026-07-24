import os
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET


def _health_response(payload: dict, *, status: int = 200) -> JsonResponse:
    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


@lru_cache(maxsize=1)
def _release_label() -> str:
    environment_label = (
        os.getenv("ALLTECH_RELEASE_SHA", "").strip()
        or os.getenv("GIT_COMMIT", "").strip()
    )
    if environment_label:
        return environment_label[:64]

    marker = Path(settings.BASE_DIR) / ".release"
    try:
        file_label = marker.read_text(encoding="utf-8").strip()
    except OSError:
        file_label = ""
    return (file_label or "unknown")[:64]


@require_GET
def live(request):
    """Process liveness check that deliberately avoids external dependencies."""

    return _health_response(
        {
            "status": "ok",
            "service": "leosoft-web",
            "release": _release_label(),
            "timestamp": timezone.now().isoformat(),
        }
    )


@require_GET
def ready(request):
    """Readiness check used only after the application and database are usable."""

    database_status = "ok"
    http_status = 200
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        database_status = "error"
        http_status = 503

    return _health_response(
        {
            "status": "ok" if http_status == 200 else "degraded",
            "service": "leosoft-web",
            "database": database_status,
            "release": _release_label(),
            "timestamp": timezone.now().isoformat(),
        },
        status=http_status,
    )


# Backwards-compatible endpoint used by existing monitors.
healthz = ready
