import json

from django.core.management.base import BaseCommand, CommandError

from customer_campaigns.services import process_scheduled_campaigns


class Command(BaseCommand):
    help = "Expire stale approvals and process due bounded customer campaign batches."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--limit", type=int, default=10)

    def handle(self, *args, **options):
        summary = process_scheduled_campaigns(
            limit=options["limit"],
            dry_run=options["dry_run"],
        )
        if options["json"]:
            self.stdout.write(json.dumps(summary, sort_keys=True))
        else:
            state = "disabled" if summary["disabled"] else "enabled"
            self.stdout.write(
                self.style.SUCCESS(
                    "Customer campaign scheduler complete — "
                    f"scheduler: {state}; "
                    f"due: {summary['due']}; "
                    f"expired: {summary['expired']}; "
                    f"processed: {summary['processed']}; "
                    f"sent: {summary['sent']}; "
                    f"suppressed: {summary['suppressed']}; "
                    f"failed: {summary['failed']}; "
                    f"paused: {summary['paused']}; "
                    f"completed: {summary['completed']}."
                )
            )
        if summary["failed"] and summary["paused"]:
            raise CommandError(
                "One or more scheduled campaigns were paused after delivery failures."
            )
