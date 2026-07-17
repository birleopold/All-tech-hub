from django.core.management.base import BaseCommand, CommandError

from automation.services import (
    process_automation_jobs,
    queue_due_growth_jobs,
    queue_due_posts,
)
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

    def handle(self, *args, **options):
        limit = max(1, min(int(options["limit"] or 100), 2000))
        dry_run = options["dry_run"]
        posts = queue_due_posts(limit=limit, dry_run=dry_run)
        growth = queue_due_growth_jobs(limit=limit, dry_run=dry_run)
        campaigns = process_scheduled_campaigns(
            limit=min(limit, 100),
            dry_run=dry_run,
        )
        jobs = (
            {"succeeded": 0, "retried": 0, "failed": 0}
            if dry_run
            else process_automation_jobs(limit=limit)
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Growth automation complete — "
                f"due posts: {posts['due']}; "
                f"social jobs queued: {posts['queued']}; "
                f"manual channels: {posts['manual']}; "
                f"due cart reminders: {growth['due_cart']}; "
                f"due product alerts: {growth['due_alerts']}; "
                f"due customer campaigns: {campaigns['due']}; "
                f"campaign batches processed: {campaigns['processed']}; "
                f"campaigns paused: {campaigns['paused']}; "
                f"jobs succeeded: {jobs['succeeded']}; "
                f"jobs retrying: {jobs['retried']}; "
                f"jobs failed: {jobs['failed']}."
            )
        )
        if jobs["failed"] or (campaigns["failed"] and campaigns["paused"]):
            raise CommandError(
                "Automation work reached permanent failure or a customer campaign "
                "was paused by its delivery-health control."
            )
