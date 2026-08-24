"""Production health checks suitable for systemd timers and monitoring agents."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone as django_timezone

from core.backups import latest_backup_status


class Command(BaseCommand):
    help = (
        "Check database, disk space, backup freshness, private-media permissions, "
        "transaction reservations, automation and email deliverability health."
    )

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json")
        parser.add_argument("--max-backup-age-hours", type=int, default=30)
        parser.add_argument("--minimum-free-disk-percent", type=float, default=15.0)
        parser.add_argument(
            "--reservation-grace-minutes",
            type=int,
            default=30,
            help="Allowed timer delay before an overdue reservation is unhealthy.",
        )
        parser.add_argument(
            "--automation-heartbeat-minutes",
            type=int,
            default=getattr(settings, "AUTOMATION_HEARTBEAT_MAX_AGE_MINUTES", 30),
        )

    def handle(self, *args, **options):
        checks = []
        failures = []

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            checks.append({"name": "database", "status": "ok"})
        except Exception as exc:
            failures.append(f"database: {exc}")
            checks.append({"name": "database", "status": "error"})

        disk = shutil.disk_usage(settings.BASE_DIR)
        free_percent = (disk.free / disk.total * 100) if disk.total else 0
        disk_status = (
            "ok"
            if free_percent >= options["minimum_free_disk_percent"]
            else "error"
        )
        checks.append(
            {
                "name": "disk",
                "status": disk_status,
                "free_percent": round(free_percent, 2),
            }
        )
        if disk_status == "error":
            failures.append(f"disk: only {free_percent:.1f}% free")

        backup = latest_backup_status()
        backup_status = (
            "ok"
            if backup.healthy
            and backup.age_hours is not None
            and backup.age_hours <= options["max_backup_age_hours"]
            else "error"
        )
        checks.append(
            {
                "name": "backup",
                "status": backup_status,
                "age_hours": (
                    round(backup.age_hours, 2)
                    if backup.age_hours is not None
                    else None
                ),
                "path": str(backup.path) if backup.path else "",
                "detail": backup.detail,
            }
        )
        if not backup.healthy:
            failures.append(f"backup: {backup.detail}")
        elif backup_status == "error":
            failures.append(
                f"backup: newest verified backup is {backup.age_hours:.1f}h old"
            )

        private_root = Path(settings.PRIVATE_MEDIA_ROOT)
        if not private_root.exists():
            checks.append(
                {"name": "private_media", "status": "warning", "detail": "not created"}
            )
        else:
            mode = private_root.stat().st_mode & 0o777
            private_status = "ok" if mode & 0o007 == 0 else "error"
            checks.append(
                {
                    "name": "private_media",
                    "status": private_status,
                    "mode": oct(mode),
                }
            )
            if private_status == "error":
                failures.append(
                    f"private_media: directory is accessible to other users ({oct(mode)})"
                )

        try:
            from reliability.models import OrderReservation

            cutoff = django_timezone.now() - timedelta(
                minutes=max(0, options["reservation_grace_minutes"])
            )
            overdue_count = OrderReservation.objects.filter(
                status=OrderReservation.STATUS_RESERVED,
                expires_at__lt=cutoff,
            ).count()
            reservation_status = "ok" if overdue_count == 0 else "error"
            checks.append(
                {
                    "name": "order_reservations",
                    "status": reservation_status,
                    "overdue_count": overdue_count,
                }
            )
            if overdue_count:
                failures.append(
                    f"order_reservations: {overdue_count} reservation(s) overdue beyond grace period"
                )
        except Exception as exc:
            checks.append(
                {
                    "name": "order_reservations",
                    "status": "error",
                    "detail": str(exc),
                }
            )
            failures.append(f"order_reservations: {exc}")

        try:
            from automation.models import AutomationControl, AutomationJob

            control = AutomationControl.load()
            heartbeat_limit = max(5, options["automation_heartbeat_minutes"])
            heartbeat_cutoff = django_timezone.now() - timedelta(
                minutes=heartbeat_limit
            )
            if control.is_paused:
                checks.append(
                    {
                        "name": "automation_heartbeat",
                        "status": "warning",
                        "detail": control.pause_reason or "master pause active",
                        "last_heartbeat_at": control.last_heartbeat_at,
                    }
                )
            else:
                heartbeat_ok = bool(
                    control.last_heartbeat_at
                    and control.last_heartbeat_at >= heartbeat_cutoff
                )
                checks.append(
                    {
                        "name": "automation_heartbeat",
                        "status": "ok" if heartbeat_ok else "error",
                        "last_heartbeat_at": control.last_heartbeat_at,
                        "maximum_age_minutes": heartbeat_limit,
                    }
                )
                if not heartbeat_ok:
                    failures.append(
                        f"automation_heartbeat: no worker heartbeat within {heartbeat_limit} minutes"
                    )

            stale_cutoff = django_timezone.now() - timedelta(
                minutes=max(
                    5,
                    int(getattr(settings, "AUTOMATION_STALE_JOB_MINUTES", 15)),
                )
            )
            stale_jobs = AutomationJob.objects.filter(
                status=AutomationJob.STATUS_RUNNING,
                locked_at__lt=stale_cutoff,
            ).count()
            checks.append(
                {
                    "name": "automation_stale_jobs",
                    "status": "ok" if stale_jobs == 0 else "error",
                    "count": stale_jobs,
                }
            )
            if stale_jobs:
                failures.append(f"automation_stale_jobs: {stale_jobs} stale running job(s)")

            dead_letters = AutomationJob.objects.filter(
                status=AutomationJob.STATUS_FAILED
            ).count()
            checks.append(
                {
                    "name": "automation_dead_letters",
                    "status": "ok" if dead_letters == 0 else "error",
                    "count": dead_letters,
                }
            )
            if dead_letters:
                failures.append(
                    f"automation_dead_letters: {dead_letters} failed job(s) require review"
                )
        except Exception as exc:
            checks.append(
                {
                    "name": "automation",
                    "status": "error",
                    "detail": str(exc),
                }
            )
            failures.append(f"automation: {exc}")

        try:
            from messaging.reporting import email_deliverability_findings

            delivery = email_deliverability_findings()
            checks.append(
                {
                    "name": "email_deliverability",
                    "status": "ok" if delivery["errors"] == 0 else "error",
                    "integrity_errors": delivery["errors"],
                    "stale_queued": delivery["stale_queued"],
                    "unprotected_bounces": delivery[
                        "bounced_without_suppression"
                    ],
                    "unprotected_complaints": delivery[
                        "complaints_without_suppression"
                    ],
                }
            )
            if delivery["errors"]:
                failures.append(
                    "email_deliverability: "
                    f"{delivery['errors']} ledger or suppression integrity error(s)"
                )
        except Exception as exc:
            checks.append(
                {
                    "name": "email_deliverability",
                    "status": "error",
                    "detail": str(exc),
                }
            )
            failures.append(f"email_deliverability: {exc}")

        payload = {
            "status": "error" if failures else "ok",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
        }
        if options["as_json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True, default=str))
        else:
            for check in checks:
                self.stdout.write(
                    f"{check['name']}: {check['status']}"
                    + (f" ({check.get('detail')})" if check.get("detail") else "")
                )

        if failures:
            raise CommandError("Operational health check failed — " + "; ".join(failures))
