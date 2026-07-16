from __future__ import annotations

import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from automation.models import AutomationJob


class Command(BaseCommand):
    help = "Check durable automation backlog, stale workers and permanent failures."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json")
        parser.add_argument(
            "--max-queued-age-minutes",
            type=int,
            default=30,
        )
        parser.add_argument(
            "--stale-running-minutes",
            type=int,
            default=20,
        )
        parser.add_argument(
            "--allow-failed",
            action="store_true",
            help="Report permanent failures without returning a failing exit code.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        queued_cutoff = now - timedelta(
            minutes=max(5, options["max_queued_age_minutes"])
        )
        running_cutoff = now - timedelta(
            minutes=max(5, options["stale_running_minutes"])
        )

        old_queue = AutomationJob.objects.filter(
            status__in=[AutomationJob.STATUS_QUEUED, AutomationJob.STATUS_RETRY],
            next_attempt_at__lt=queued_cutoff,
        )
        stale_running = AutomationJob.objects.filter(
            status=AutomationJob.STATUS_RUNNING,
            locked_at__lt=running_cutoff,
        )
        failed = AutomationJob.objects.filter(status=AutomationJob.STATUS_FAILED)

        payload = {
            "status": "error"
            if old_queue.exists()
            or stale_running.exists()
            or (failed.exists() and not options["allow_failed"])
            else "ok",
            "checked_at": now.isoformat(),
            "counts": {
                "old_queued_or_retrying": old_queue.count(),
                "stale_running": stale_running.count(),
                "permanent_failures": failed.count(),
            },
            "samples": {
                "old_queued_or_retrying": list(
                    old_queue.order_by("next_attempt_at")
                    .values_list("idempotency_key", flat=True)[:10]
                ),
                "stale_running": list(
                    stale_running.order_by("locked_at")
                    .values_list("idempotency_key", flat=True)[:10]
                ),
                "permanent_failures": list(
                    failed.order_by("completed_at", "id")
                    .values_list("idempotency_key", flat=True)[:10]
                ),
            },
        }

        if options["as_json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True))
        else:
            for name, count in payload["counts"].items():
                self.stdout.write(f"{name}: {count}")

        failures = []
        if payload["counts"]["old_queued_or_retrying"]:
            failures.append("automation queue is not being drained")
        if payload["counts"]["stale_running"]:
            failures.append("automation workers have stale running locks")
        if payload["counts"]["permanent_failures"] and not options["allow_failed"]:
            failures.append("automation jobs require manual investigation")
        if failures:
            raise CommandError("Automation health check failed — " + "; ".join(failures))
