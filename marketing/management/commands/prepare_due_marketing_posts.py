from django.core.management.base import BaseCommand
from django.utils import timezone

from marketing.models import ScheduledPost


class Command(BaseCommand):
    help = "Move due scheduled marketing posts into the Ready to publish queue."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many posts are due without updating them.",
        )

    def handle(self, *args, **options):
        due = ScheduledPost.objects.filter(
            status=ScheduledPost.STATUS_SCHEDULED,
            scheduled_for__isnull=False,
            scheduled_for__lte=timezone.now(),
        )
        count = due.count()
        if options["dry_run"]:
            self.stdout.write(f"Due posts: {count}")
            return
        updated = due.update(status=ScheduledPost.STATUS_READY)
        self.stdout.write(self.style.SUCCESS(f"Prepared {updated} due marketing post(s)."))
