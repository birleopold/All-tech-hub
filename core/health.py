from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.utils import timezone


def healthz(request):
    """Return a small, read-only readiness response for uptime monitoring."""

    database_status = "ok"
    http_status = 200

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        database_status = "error"
        http_status = 503

    response = JsonResponse(
        {
            "status": "ok" if http_status == 200 else "degraded",
            "database": database_status,
            "timestamp": timezone.now().isoformat(),
        },
        status=http_status,
    )
    response["Cache-Control"] = "no-store, max-age=0"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response
