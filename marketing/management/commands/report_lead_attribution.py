"""Read-only attribution and overdue lead health report."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from marketing.models import MarketingLead


class Command(BaseCommand):
    help = "Audit the source and ownership of leads without altering customer records."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90)

    def handle(self, *args, **options):
        days = options["days"]
        if not 1 <= days <= 365:
            self.stderr.write("--days must be between 1 and 365")
            return
        leads = MarketingLead.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=days)
        )
        now = timezone.now()
        active = leads.exclude(
            status__in=(MarketingLead.STATUS_WON, MarketingLead.STATUS_LOST)
        )
        overdue = active.filter(
            Q(next_follow_up_at__lte=now)
            | Q(status=MarketingLead.STATUS_NEW,
                first_contacted_at__isnull=True, response_due_at__lte=now)
        ).distinct()
        self.stdout.write(
            f"Last {days} days: {leads.count()} leads; "
            f"{overdue.count()} overdue; "
            f"{overdue.filter(assigned_to__isnull=True).count()} overdue unassigned"
        )
        self.stdout.write("Recorded sources (unverified direct means no campaign proof):")
        for entry in leads.values("source").annotate(count=Count("pk")).order_by("-count", "source"):
            self.stdout.write(f'{entry["source"] or "unrecorded"}: {entry["count"]}')
        self.stdout.write(
            f'Linked to a tracked campaign: '
            f'{leads.filter(Q(campaign__isnull=False) | Q(link__isnull=False)).distinct().count()}'
        )
        self.stdout.write("No attribution or lead ownership data changed.")
