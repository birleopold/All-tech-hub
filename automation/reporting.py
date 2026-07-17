from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from automation.models import AutomationControl, AutomationJob, AutomationRun


def _setting_int(name: str, default: int, *, minimum: int = 1, maximum: int = 10080) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def automation_control_summary() -> dict:
    now = timezone.now()
    control = AutomationControl.load()
    heartbeat_minutes = _setting_int(
        "AUTOMATION_HEARTBEAT_MAX_AGE_MINUTES",
        30,
        minimum=5,
        maximum=1440,
    )
    stale_minutes = _setting_int(
        "AUTOMATION_STALE_JOB_MINUTES",
        15,
        minimum=5,
        maximum=1440,
    )
    heartbeat_cutoff = now - timedelta(minutes=heartbeat_minutes)
    stale_cutoff = now - timedelta(minutes=stale_minutes)

    status_counts = {
        row["status"]: row["count"]
        for row in AutomationJob.objects.values("status").annotate(count=Count("id"))
    }
    type_counts = {
        row["job_type"]: row["count"]
        for row in AutomationJob.objects.values("job_type").annotate(count=Count("id"))
    }
    due_jobs = AutomationJob.objects.filter(
        status__in=[AutomationJob.STATUS_QUEUED, AutomationJob.STATUS_RETRY],
        next_attempt_at__lte=now,
    ).count()
    stale_running = AutomationJob.objects.filter(
        status=AutomationJob.STATUS_RUNNING,
        locked_at__lt=stale_cutoff,
    ).count()
    recent_failures = AutomationJob.objects.filter(
        status=AutomationJob.STATUS_FAILED,
        completed_at__gte=now - timedelta(hours=24),
    ).count()
    heartbeat_stale = (
        control.last_heartbeat_at is None or control.last_heartbeat_at < heartbeat_cutoff
    )

    return {
        "control": control,
        "heartbeat_stale": heartbeat_stale,
        "heartbeat_minutes": heartbeat_minutes,
        "stale_minutes": stale_minutes,
        "status_counts": status_counts,
        "type_counts": type_counts,
        "due_jobs": due_jobs,
        "stale_running": stale_running,
        "recent_failures": recent_failures,
        "recent_runs": AutomationRun.objects.all()[:30],
        "failed_jobs": AutomationJob.objects.filter(
            status=AutomationJob.STATUS_FAILED
        ).order_by("completed_at", "id")[:100],
        "open_jobs": AutomationJob.objects.filter(
            status__in=[
                AutomationJob.STATUS_QUEUED,
                AutomationJob.STATUS_RUNNING,
                AutomationJob.STATUS_RETRY,
            ]
        ).order_by("next_attempt_at", "id")[:100],
    }


def automation_integrity_findings() -> dict:
    now = timezone.now()
    summary = automation_control_summary()
    control = summary["control"]
    stale_cutoff = now - timedelta(minutes=summary["stale_minutes"])
    heartbeat_error = int(summary["heartbeat_stale"] and not control.is_paused)
    pause_without_reason = int(control.is_paused and not control.pause_reason.strip())
    valid_types = set(dict(AutomationJob.TYPE_CHOICES))
    invalid_paused_types = sorted(
        set(str(value) for value in (control.paused_job_types or [])) - valid_types
    )
    stale_running_jobs = list(
        AutomationJob.objects.filter(
            status=AutomationJob.STATUS_RUNNING,
            locked_at__lt=stale_cutoff,
        )
        .order_by("locked_at", "id")
        .values("id", "idempotency_key", "job_type", "locked_at", "locked_by")[:50]
    )
    running_without_lock = AutomationJob.objects.filter(
        status=AutomationJob.STATUS_RUNNING,
    ).filter(Q(locked_at__isnull=True) | Q(locked_by="")).count()
    terminal_without_completion = AutomationJob.objects.filter(
        status__in=[
            AutomationJob.STATUS_SUCCEEDED,
            AutomationJob.STATUS_FAILED,
            AutomationJob.STATUS_CANCELLED,
        ],
        completed_at__isnull=True,
    ).count()
    dead_letter_jobs = AutomationJob.objects.filter(
        status=AutomationJob.STATUS_FAILED
    ).count()
    stale_runs = list(
        AutomationRun.objects.filter(
            status=AutomationRun.STATUS_RUNNING,
            started_at__lt=stale_cutoff,
        )
        .order_by("started_at", "id")
        .values("id", "source", "worker_id", "started_at")[:50]
    )
    control_stuck_running = int(
        control.last_run_status == AutomationControl.RUN_RUNNING
        and (
            control.last_run_started_at is None
            or control.last_run_started_at < stale_cutoff
        )
    )
    errors = (
        heartbeat_error
        + pause_without_reason
        + len(invalid_paused_types)
        + len(stale_running_jobs)
        + running_without_lock
        + terminal_without_completion
        + dead_letter_jobs
        + len(stale_runs)
        + control_stuck_running
    )
    return {
        "errors": errors,
        "heartbeat_error": heartbeat_error,
        "heartbeat_stale": summary["heartbeat_stale"],
        "heartbeat_minutes": summary["heartbeat_minutes"],
        "pause_without_reason": pause_without_reason,
        "invalid_paused_types": invalid_paused_types,
        "stale_running_count": len(stale_running_jobs),
        "stale_running_jobs": stale_running_jobs,
        "running_without_lock": running_without_lock,
        "terminal_without_completion": terminal_without_completion,
        "dead_letter_jobs": dead_letter_jobs,
        "stale_run_count": len(stale_runs),
        "stale_runs": stale_runs,
        "control_stuck_running": control_stuck_running,
        "job_count": AutomationJob.objects.count(),
        "run_count": AutomationRun.objects.count(),
        "control_paused": control.is_paused,
        "paused_job_types": control.paused_job_types or [],
        "last_heartbeat_at": control.last_heartbeat_at,
        "last_run_status": control.last_run_status,
        "consecutive_failures": control.consecutive_failures,
    }
