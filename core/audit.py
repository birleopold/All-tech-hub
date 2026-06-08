from __future__ import annotations

from django.db import models

from core.models import AuditEvent


def log_audit_event(
    *,
    actor,
    verb: str,
    summary: str,
    target: models.Model | None = None,
) -> AuditEvent:
    """Persist a single audit row."""
    tt = ""
    tid: int | None = None
    if target is not None:
        tt = f"{target._meta.app_label}.{target._meta.model_name}"
        pk = target.pk
        tid = int(pk) if pk is not None else None
    return AuditEvent.objects.create(
        actor=actor,
        verb=verb[:64],
        summary=summary[:500],
        target_type=tt[:80],
        target_id=tid,
    )
