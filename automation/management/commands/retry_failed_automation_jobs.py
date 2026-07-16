from django.core.management.base import BaseCommand

from automation.services import retry_failed_jobs


class Command(BaseCommand):
    help = "Reset permanently failed automation jobs so they can be attempted again."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        count = retry_failed_jobs(limit=max(1, min(options["limit"], 2000)))
        self.stdout.write(self.style.SUCCESS(f"Automation jobs requeued: {count}."))
