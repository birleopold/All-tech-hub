import os
from pathlib import Path

from django.conf import settings
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET


def _health_response(payload: dict, *, status: int = 200) -> JsonResponse:
    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


def _read_release_label() -> str:
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


# Pin the revision when the worker imports this module. An old worker must not
# claim a newly written release marker before systemd has actually replaced it.
RUNNING_RELEASE = _read_release_label()


@require_GET
def live(request):
    """Process liveness check that deliberately avoids external dependencies."""

    return _health_response(
        {
            "status": "ok",
            "service": "leosoft-web",
            "release": RUNNING_RELEASE,
            "timestamp": timezone.now().isoformat(),
        }
    )


@require_GET
def ready(request):
    """Readiness check used only after the application and database are usable."""

    database_status = "ok"
    migration_status = "unknown"
    pending_migrations = []
    http_status = 200
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        pending_migrations = [
            f"{migration.app_label}.{migration.name}"
            for migration, backwards in plan
            if not backwards
        ][:20]
        migration_status = "pending" if pending_migrations else "ok"
        if pending_migrations:
            http_status = 503
    except DatabaseError:
        database_status = "error"
        migration_status = "error"
        http_status = 503

    return _health_response(
        {
            "status": "ok" if http_status == 200 else "degraded",
            "service": "leosoft-web",
            "database": database_status,
            "migrations": migration_status,
            "pending_migrations": pending_migrations,
            "release": RUNNING_RELEASE,
            "timestamp": timezone.now().isoformat(),
        },
        status=http_status,
    )


# Backwards-compatible endpoint used by existing monitors.
healthz = ready
