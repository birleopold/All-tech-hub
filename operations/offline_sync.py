"""Strict, review-before-replay synchronization for offline technician notes.

Only staff-authored INTERNAL text notes can be queued offline. Never replay
job state, stock, expenses, signatures, photos or payment operations.
"""
from __future__ import annotations

from uuid import UUID

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from operations.models import JobCard, JobNote


def _reply(status: int, message: str, *, code: str, **extras):
    response = JsonResponse({"code": code, "message": message, **extras}, status=status)
    response["Cache-Control"] = "no-store"
    return response


@require_POST
@transaction.atomic
def offline_job_note_sync(request, pk: int):
    """Replay one staff-reviewed internal note, with an idempotency key."""
    if not request.user.is_authenticated:
        return _reply(401, "Sign in again before syncing.", code="auth_required")
    if not request.user.is_staff or not request.user.has_perm("operations.add_jobnote"):
        return _reply(403, "Your account cannot add technician notes.", code="forbidden")

    raw_key = (request.POST.get("operation_id") or "").strip()
    try:
        key = UUID(raw_key, version=4)
        if str(key) != raw_key:
            raise ValueError("Non-canonical identifier")
    except (ValueError, AttributeError, TypeError):
        return _reply(400, "Invalid note identifier.", code="invalid_key")

    note_text = (request.POST.get("body") or "").strip()
    base_version = (request.POST.get("base_version") or "").strip()
    if not 1 <= len(note_text) <= 3000 or not base_version or len(base_version) > 80:
        return _reply(400, "Enter a note under 3,000 characters and retain its original version.", code="invalid_note")

    # Check replay identity before attempting to evaluate a stale job version.
    # Different users cannot cause each other's note to be silently confirmed.
    previous = JobNote.objects.select_for_update().filter(client_operation_id=key).first()
    if previous:
        if (
            previous.job_id == pk
            and previous.author_id == request.user.pk
            and previous.is_internal
            and previous.body == note_text
        ):
            return _reply(200, "This note was already saved.", code="already_saved", note_id=previous.pk)
        return _reply(409, "That note identifier was used for different content.", code="key_conflict")

    job = get_object_or_404(JobCard.objects.select_for_update(), pk=pk)
    if not job.is_open:
        return _reply(409, "This job is now closed. Review before recording further work.", code="job_closed")
    current_version = job.updated_at.isoformat()
    if base_version != current_version:
        return _reply(
            409, "The job changed after this note was drafted. Review the latest job before retrying.",
            code="job_changed", current_version=current_version,
        )

    try:
        with transaction.atomic():
            created = JobNote.objects.create(
                job=job, author=request.user, body=note_text,
                client_operation_id=key, is_internal=True,
            )
    except IntegrityError:
        previous = JobNote.objects.filter(client_operation_id=key).first()
        if previous and previous.job_id == pk and previous.author_id == request.user.pk and previous.is_internal and previous.body == note_text:
            return _reply(200, "Already saved.", code="already_saved", note_id=previous.pk)
        return _reply(409, "Operation ID already used.", code="key_conflict")
    return _reply(201, "Internal field note saved.", code="saved", note_id=created.pk)
