from django.core.management.base import BaseCommand

from reports.followups import refresh_retention_followups


class Command(BaseCommand):
    help = "Create idempotent customer-care tasks for expiring warranties and dormant customers."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        result = refresh_retention_followups(
            limit=options["limit"], dry_run=options["dry_run"]
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Retention follow-up refresh complete — "
                f"warranty: {result['warranty_created']}; "
                f"dormant: {result['dormant_created']}; "
                f"existing: {result['existing']}; "
                f"dry run: {result['dry_run']}."
            )
        )
