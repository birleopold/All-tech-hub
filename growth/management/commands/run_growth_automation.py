from django.core.management.base import BaseCommand, CommandError

from automation.control import (
    automation_control,
    finish_automation_run,
    start_automation_run,
)
from automation.models import AutomationRun
from automation.services import queue_due_growth_jobs, queue_due_posts
from automation.worker import process_controlled_automation_jobs
from customer_campaigns.services import process_scheduled_campaigns


class Command(BaseCommand):
    help = (
        "Queue and process durable marketing, customer campaign, saved-cart and "
        "stock-alert jobs. Kept for compatibility with the existing systemd service."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show due work without changing records or sending anything.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum records queued or processed per category.",
        )
        parser.add_argument(
            "--source",
            choices=[AutomationRun.SOURCE_TIMER, AutomationRun.SOURCE_MANUAL],
            default=AutomationRun.SOURCE_TIMER,
            help="Record whether this invocation came from the timer or a manual command.",
        )

    def handle(self, *args, **options):
        limit = max(1, min(int(options["limit"] or 100), 2000))
        dry_run = options["dry_run"]
        run = start_automation_run(source=options["source"])
        try:
            control = automation_control()
            blocked = bool(control.is_paused)
            inspect_only = dry_run or blocked
            posts = queue_due_posts(limit=limit, dry_run=inspect_only)
            growth = queue_due_growth_jobs(limit=limit, dry_run=inspect_only)
            campaigns = process_scheduled_campaigns(
                limit=min(limit, 100),
                dry_run=inspect_only,
            )
            jobs = (
                {
                    "succeeded": 0,
                    "retried": 0,
                    "failed": 0,
                    "recovered": 0,
                    "paused": blocked,
                }
                if inspect_only
                else process_controlled_automation_jobs(
                    limit=limit,
                    worker_id=run.worker_id,
                )
            )
            summary = {
                "paused": blocked,
                "dry_run": dry_run,
                "posts": posts,
                "growth": growth,
                "campaigns": campaigns,
                "jobs": jobs,
            }
            has_failures = bool(
                jobs["failed"] or (campaigns["failed"] and campaigns["paused"])
            )
            if dry_run:
                run_status = AutomationRun.STATUS_DRY
            elif blocked:
                run_status = AutomationRun.STATUS_PAUSED
            elif has_failures:
                run_status = AutomationRun.STATUS_PARTIAL
            else:
                run_status = AutomationRun.STATUS_SUCCEEDED
            finish_automation_run(run, status=run_status, summary=summary)

            self.stdout.write(
                self.style.SUCCESS(
                    "Growth automation complete — "
                    f"source: {options['source']}; "
                    f"master paused: {blocked}; "
                    f"due posts: {posts['due']}; "
                    f"social jobs queued: {posts['queued']}; "
                    f"manual channels: {posts['manual']}; "
                    f"due cart reminders: {growth['due_cart']}; "
                    f"due product alerts: {growth['due_alerts']}; "
                    f"due customer campaigns: {campaigns['due']}; "
                    f"campaign batches processed: {campaigns['processed']}; "
                    f"campaigns paused: {campaigns['paused']}; "
                    f"jobs recovered: {jobs['recovered']}; "
                    f"jobs succeeded: {jobs['succeeded']}; "
                    f"jobs retrying: {jobs['retried']}; "
                    f"jobs failed: {jobs['failed']}."
                )
            )
            if has_failures:
                raise CommandError(
                    "Automation work reached permanent failure or a customer campaign "
                    "was paused by its delivery-health control."
                )
        except CommandError:
            raise
        except Exception as exc:
            finish_automation_run(
                run,
                status=AutomationRun.STATUS_FAILED,
                error=str(exc),
            )
            raise
