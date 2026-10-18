"""Read-only diagnostic of repeated staff notifications."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Min
from django.utils import timezone

from core.models import StaffNotification


class Command(BaseCommand):
    help = "Report repeated staff alerts; no records are changed."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        days, limit = options["days"], options["limit"]
        if not 1 <= days <= 365 or not 1 <= limit <= 100:
            self.stderr.write("Use --days 1..365 and --limit 1..100")
            return
        alerts = StaffNotification.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=days)
        )
        total = alerts.count()
        unread = alerts.filter(is_read=False).count()
        groups = (
            alerts.values("recipient_id", "message", "link")
            .annotate(copies=Count("pk"), first=Min("created_at"), last=Max("created_at"))
            .filter(copies__gt=1)
            .order_by("-copies", "recipient_id")[:limit]
        )
        self.stdout.write(f"Period: {days} days; total={total}; unread={unread}")
        self.stdout.write("Repeated alert groups (recipient id, count, first, last, message):")
        for group in groups:
            self.stdout.write(
                f'{group["recipient_id"]} | {group["copies"]} | '
                f'{group["first"]} | {group["last"]} | '
                f'{group["message"][:120]}'
            )
        self.stdout.write("Read-only. No notifications were deleted or marked read.")
