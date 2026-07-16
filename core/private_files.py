"""Permission-checked delivery helpers for sensitive uploaded files."""

from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath
from urllib.parse import quote

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse


def _safe_storage_name(name: str) -> str:
    path = PurePosixPath((name or "").replace("\\", "/"))
    if not name or path.is_absolute() or ".." in path.parts:
        raise Http404("File not found.")
    return str(path)


def protected_file_response(field_file, *, inline: bool = True, filename: str = ""):
    """Return a no-store response after the calling view checks permission.

    Production delegates the bytes to an internal Nginx location using
    ``X-Accel-Redirect``. Development and tests stream through Django.
    """

    if not field_file or not getattr(field_file, "name", ""):
        raise Http404("File not found.")

    storage_name = _safe_storage_name(field_file.name)
    download_name = (filename or PurePosixPath(storage_name).name).replace('"', "")
    disposition = "inline" if inline else "attachment"
    content_type = mimetypes.guess_type(download_name)[0] or "application/octet-stream"

    if getattr(settings, "PRIVATE_MEDIA_USE_X_ACCEL", not settings.DEBUG):
        response = HttpResponse(content_type=content_type)
        response["X-Accel-Redirect"] = "/protected-media/" + quote(
            storage_name,
            safe="/",
        )
        try:
            response["Content-Length"] = str(field_file.storage.size(storage_name))
        except (OSError, NotImplementedError):
            pass
    else:
        try:
            field_file.open("rb")
        except (FileNotFoundError, OSError):
            raise Http404("File not found.")
        response = FileResponse(field_file, content_type=content_type)

    response["Content-Disposition"] = f'{disposition}; filename="{download_name}"'
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    return response
