from __future__ import annotations

import os
import socket
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from automation.models import (
    AutomationControl,
    AutomationJob,
    AutomationJobEvent,
    AutomationRun,
    PostChannelDelivery,
)
from core.audit import log_audit_event


class AutomationControlError(Exception):
    pass


VALID_JOB_TYPES = {value for value, _label in AutomationJob.TYPE_CHOICES}


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def record_job_event(
    job: AutomationJob,
    action: str,
    *,
    actor=None,
    message: str = "",
    metadata: dict | None = None,
) -> AutomationJobEvent:
    return AutomationJobEvent.objects.create(
        job=job,
        action=action,
        actor=actor,
        message=(message or "")[:500],
        metadata=metadata or {},
    )


def normalise_job_types(values) -> list[str]:
    return sorted({str(value) for value in (values or []) if str(value) in VALID_JOB_TYPES})


def automation_control() -> AutomationControl:
    return AutomationControl.load()


def is_automation_paused(*, job_type: str | None = None) -> bool:
    control = AutomationControl.load()
    if control.is_paused:
        return True
    return bool(job_type and job_type in normalise_job_types(control.paused_job_types))


@transaction.atomic
def pause_automation(*, user, reason: str, job_types=None) -> AutomationControl:
    control = AutomationControl.objects.select_for_update().filter(
        singleton_key="primary"
    ).first()
    if control is None:
        control = AutomationControl.objects.create(singleton_key="primary")
    now = timezone.now()
    selected = normalise_job_types(job_types)
    reason = (reason or "Automation paused for operational review.").strip()[:300]
    if selected:
        control.paused_job_types = sorted(
            set(normalise_job_types(control.paused_job_types)) | set(selected)
        )
    else:
        control.is_paused = True
    control.pause_reason = reason
    control.paused_by = user
    control.paused_at = now
    control.last_run_status = AutomationControl.RUN_PAUSED
    control.save(
        update_fields=[
            "is_paused",
            "paused_job_types",
            "pause_reason",
            "paused_by",
            "paused_at",
            "last_run_status",
            "updated_at",
        ]
    )
    scope = ", ".join(selected) if selected else "all automation"
    log_audit_event(
        actor=user,
        verb="automation.control_paused",
        summary=f"Paused {scope}: {reason}",
        target=control,
    )
    return control


@transaction.atomic
def resume_automation(*, user, job_types=None) -> AutomationControl:
    control = AutomationControl.objects.select_for_update().filter(
        singleton_key="primary"
    ).first()
    if control is None:
        control = AutomationControl.objects.create(singleton_key="primary")
    selected = normalise_job_types(job_types)
    if selected:
        control.paused_job_types = sorted(
            set(normalise_job_types(control.paused_job_types)) - set(selected)
        )
        scope = ", ".join(selected)
    else:
        control.is_paused = False
        control.paused_job_types = []
        scope = "all automation"
    control.resumed_by = user
    control.resumed_at = timezone.now()
    if not control.is_paused and not control.paused_job_types:
        control.pause_reason = ""
        control.paused_by = None
        control.paused_at = None
    control.save(
        update_fields=[
            "is_paused",
            "paused_job_types",
            "pause_reason",
            "paused_by",
            "paused_at",
            "resumed_by",
            "resumed_at",
            "updated_at",
        ]
    )
    log_audit_event(
        actor=user,
        verb="automation.control_resumed",
        summary=f"Resumed {scope}.",
        target=control,
    )
    return control


@transaction.atomic
def start_automation_run(
    *,
    source: str = AutomationRun.SOURCE_TIMER,
    worker_id: str = "",
) -> AutomationRun:
    worker_id = (worker_id or worker_identity())[:160]
    run = AutomationRun.objects.create(
        source=source,
        status=AutomationRun.STATUS_RUNNING,
        worker_id=worker_id,
    )
    now = timezone.now()
    control = AutomationControl.objects.select_for_update().filter(
        singleton_key="primary"
    ).first()
    if control is None:
        control = AutomationControl.objects.create(singleton_key="primary")
    control.last_heartbeat_at = now
    control.last_run_started_at = now
    control.last_run_status = AutomationControl.RUN_RUNNING
    control.last_worker_id = worker_id
    control.save(
        update_fields=[
            "last_heartbeat_at",
            "last_run_started_at",
            "last_run_status",
            "last_worker_id",
            "updated_at",
        ]
    )
    return run


@transaction.atomic
def finish_automation_run(
    run: AutomationRun,
    *,
    status: str,
    summary: dict | None = None,
    error: str = "",
) -> AutomationRun:
    now = timezone.now()
    run = AutomationRun.objects.select_for_update().get(pk=run.pk)
    run.status = status
    run.summary = summary or {}
    run.error = (error or "")[:4000]
    run.finished_at = now
    run.save(update_fields=["status", "summary", "error", "finished_at"])

    control = AutomationControl.objects.select_for_update().filter(
        singleton_key="primary"
    ).first()
    if control is None:
        control = AutomationControl.objects.create(singleton_key="primary")
    status_map = {
        AutomationRun.STATUS_SUCCEEDED: AutomationControl.RUN_SUCCEEDED,
        AutomationRun.STATUS_PARTIAL: AutomationControl.RUN_PARTIAL,
        AutomationRun.STATUS_FAILED: AutomationControl.RUN_FAILED,
        AutomationRun.STATUS_PAUSED: AutomationControl.RUN_PAUSED,
        AutomationRun.STATUS_DRY: AutomationControl.RUN_DRY,
    }
    control.last_heartbeat_at = now
    control.last_run_finished_at = now
    control.last_run_status = status_map.get(status, AutomationControl.RUN_FAILED)
    control.last_summary = run.summary
    if status in {AutomationRun.STATUS_FAILED, AutomationRun.STATUS_PARTIAL}:
        control.consecutive_failures += 1
    else:
        control.consecutive_failures = 0
    control.save(
        update_fields=[
            "last_heartbeat_at",
            "last_run_finished_at",
            "last_run_status",
            "last_summary",
            "consecutive_failures",
            "updated_at",
        ]
    )
    return run


def heartbeat_is_stale(*, max_age_minutes: int = 30) -> bool:
    control = AutomationControl.load()
    if control.last_heartbeat_at is None:
        return True
    cutoff = timezone.now() - timedelta(minutes=max(5, max_age_minutes))
    return control.last_heartbeat_at < cutoff


@transaction.atomic
def replay_failed_job(job: AutomationJob, *, user) -> AutomationJob:
    job = AutomationJob.objects.select_for_update().get(pk=job.pk)
    previous_status = job.status
    previous_error = job.last_error
    if job.status not in {
        AutomationJob.STATUS_FAILED,
        AutomationJob.STATUS_CANCELLED,
    }:
        raise AutomationControlError("Only failed or cancelled jobs can be replayed.")
    if job.job_type == AutomationJob.TYPE_SOCIAL_POST:
        record_job_event(
            job,
            AutomationJobEvent.ACTION_BLOCKED,
            actor=user,
            message=(
                "Social-post replay blocked because external publication may be uncertain. "
                "Verify the platform and rebuild the scheduled post instead."
            ),
            metadata={"previous_status": previous_status},
        )
        raise AutomationControlError(
            "Social-post replay is blocked. Verify the external platform and rebuild the post."
        )
    if job.delivery_id:
        delivery = PostChannelDelivery.objects.select_for_update().get(pk=job.delivery_id)
        if delivery.status == PostChannelDelivery.STATUS_PUBLISHED:
            raise AutomationControlError("A published delivery cannot be replayed.")
        delivery.status = PostChannelDelivery.STATUS_QUEUED
        delivery.next_attempt_at = timezone.now()
        delivery.last_error = ""
        delivery.save(
            update_fields=["status", "next_attempt_at", "last_error", "updated_at"]
        )

    now = timezone.now()
    job.status = AutomationJob.STATUS_QUEUED
    job.next_attempt_at = now
    job.attempt_count = 0
    job.completed_at = None
    job.locked_at = None
    job.locked_by = ""
    job.last_error = ""
    job.result = {}
    job.save(
        update_fields=[
            "status",
            "next_attempt_at",
            "attempt_count",
            "completed_at",
            "locked_at",
            "locked_by",
            "last_error",
            "result",
            "updated_at",
        ]
    )
    record_job_event(
        job,
        AutomationJobEvent.ACTION_REPLAYED,
        actor=user,
        message="Failed automation job returned to the queue after staff review.",
        metadata={
            "previous_status": previous_status,
            "previous_error": previous_error[:1000],
        },
    )
    log_audit_event(
        actor=user,
        verb="automation.job_replayed",
        summary=f"Replayed automation job {job.idempotency_key}.",
        target=job,
    )
    return job


@transaction.atomic
def cancel_open_job(job: AutomationJob, *, user, reason: str = "") -> AutomationJob:
    job = AutomationJob.objects.select_for_update().get(pk=job.pk)
    if job.status == AutomationJob.STATUS_RUNNING:
        raise AutomationControlError(
            "A running job cannot be cancelled because its external result may be uncertain."
        )
    if job.is_terminal:
        raise AutomationControlError("This job is already in a terminal state.")
    now = timezone.now()
    message = (reason or "Cancelled by authorised staff.").strip()[:4000]
    job.status = AutomationJob.STATUS_CANCELLED
    job.completed_at = now
    job.locked_at = None
    job.locked_by = ""
    job.last_error = message
    job.save(
        update_fields=[
            "status",
            "completed_at",
            "locked_at",
            "locked_by",
            "last_error",
            "updated_at",
        ]
    )
    if job.delivery_id:
        PostChannelDelivery.objects.filter(
            pk=job.delivery_id,
        ).exclude(status=PostChannelDelivery.STATUS_PUBLISHED).update(
            status=PostChannelDelivery.STATUS_CANCELLED,
            next_attempt_at=None,
            last_error=message,
            updated_at=now,
        )
    record_job_event(
        job,
        AutomationJobEvent.ACTION_CANCELLED,
        actor=user,
        message=message,
    )
    log_audit_event(
        actor=user,
        verb="automation.job_cancelled",
        summary=f"Cancelled automation job {job.idempotency_key}: {message[:300]}",
        target=job,
    )
    return job
