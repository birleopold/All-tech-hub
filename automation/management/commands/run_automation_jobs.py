from django.core.management.base import BaseCommand, CommandError

from automation.services import (
    process_automation_jobs,
    queue_due_growth_jobs,
    queue_due_posts,
)


class Command(BaseCommand):
    help = (
        "Queue due marketing, cart and stock-alert work, then process durable "
        "automation jobs with retries."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--enqueue-only", action="store_true")
        parser.add_argument("--process-only", action="store_true")
        parser.add_argument("--worker-id", default="")

    def handle(self, *args, **options):
        if options["enqueue_only"] and options["process_only"]:
            raise CommandError("Choose either --enqueue-only or --process-only, not both.")
        limit = max(1, min(int(options["limit"] or 100), 2000))
        dry_run = options["dry_run"]

        post_result = {"due": 0, "queued": 0, "manual": 0}
        growth_result = {
            "due_cart": 0,
            "due_alerts": 0,
            "queued_cart": 0,
            "queued_alerts": 0,
        }
        job_result = {"succeeded": 0, "retried": 0, "failed": 0}

        if not options["process_only"]:
            post_result = queue_due_posts(limit=limit, dry_run=dry_run)
            growth_result = queue_due_growth_jobs(limit=limit, dry_run=dry_run)

        if not dry_run and not options["enqueue_only"]:
            job_result = process_automation_jobs(
                limit=limit,
                worker_id=options["worker_id"],
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Automation cycle complete — "
                f"due posts: {post_result['due']}; "
                f"social jobs queued: {post_result['queued']}; "
                f"manual channels: {post_result['manual']}; "
                f"due cart emails: {growth_result['due_cart']}; "
                f"due stock alerts: {growth_result['due_alerts']}; "
                f"email jobs queued: "
                f"{growth_result['queued_cart'] + growth_result['queued_alerts']}; "
                f"jobs succeeded: {job_result['succeeded']}; "
                f"jobs retrying: {job_result['retried']}; "
                f"jobs failed: {job_result['failed']}."
            )
        )
        if job_result["failed"]:
            raise CommandError(
                f"{job_result['failed']} automation job(s) reached permanent failure."
            )
