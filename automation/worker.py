from __future__ import annotations

from django.db import connection, transaction
from django.utils import timezone

from automation.control import automation_control, worker_identity
from automation.models import AutomationJob
from automation.services import (
    _execute_job,
    _finish_failure,
    _finish_success,
    recover_stale_jobs,
)
from automation.connectors import ConnectorError


@transaction.atomic
def claim_controlled_job(worker_id: str) -> AutomationJob | None:
    control = automation_control()
    if control.is_paused:
        return None
    paused_types = [
        value
        for value in (control.paused_job_types or [])
        if value in dict(AutomationJob.TYPE_CHOICES)
    ]
    queryset = AutomationJob.objects.filter(
        status__in=[AutomationJob.STATUS_QUEUED, AutomationJob.STATUS_RETRY],
        next_attempt_at__lte=timezone.now(),
    )
    if paused_types:
        queryset = queryset.exclude(job_type__in=paused_types)
    queryset = queryset.order_by("next_attempt_at", "id")
    if connection.features.has_select_for_update_skip_locked:
        queryset = queryset.select_for_update(skip_locked=True)
    else:
        queryset = queryset.select_for_update()
    job = queryset.first()
    if job is None:
        return None
    now = timezone.now()
    job.status = AutomationJob.STATUS_RUNNING
    job.attempt_count += 1
    job.locked_at = now
    job.locked_by = worker_id[:120]
    job.save(
        update_fields=[
            "status",
            "attempt_count",
            "locked_at",
            "locked_by",
            "updated_at",
        ]
    )
    if job.delivery_id:
        from automation.models import PostChannelDelivery

        PostChannelDelivery.objects.filter(pk=job.delivery_id).update(
            status=PostChannelDelivery.STATUS_RUNNING,
            attempt_count=job.attempt_count,
            last_attempt_at=now,
            next_attempt_at=None,
            updated_at=now,
        )
    return job


def process_controlled_automation_jobs(*, limit: int = 100, worker_id: str = "") -> dict:
    worker_id = worker_id or worker_identity()
    control = automation_control()
    if control.is_paused:
        return {
            "succeeded": 0,
            "retried": 0,
            "failed": 0,
            "recovered": 0,
            "paused": True,
        }
    recovered = recover_stale_jobs()
    succeeded = retried = failed = 0
    for _index in range(max(1, min(int(limit or 100), 2000))):
        job = claim_controlled_job(worker_id)
        if job is None:
            break
        try:
            result = _execute_job(job)
            _finish_success(job, result)
            succeeded += 1
        except ConnectorError as exc:
            _finish_failure(job, exc, retryable=exc.retryable)
            if exc.retryable and job.attempt_count < job.max_attempts:
                retried += 1
            else:
                failed += 1
        except Exception as exc:
            _finish_failure(job, exc, retryable=True)
            if job.attempt_count < job.max_attempts:
                retried += 1
            else:
                failed += 1
    return {
        "succeeded": succeeded,
        "retried": retried,
        "failed": failed,
        "recovered": recovered,
        "paused": False,
    }
