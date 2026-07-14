from django.core.management.base import BaseCommand
from django.utils import timezone

from growth.models import GrowthSettings, SavedCart, StockAlertSubscription
from growth.services import process_saved_cart_reminders, process_stock_alerts
from marketing.models import ScheduledPost


class Command(BaseCommand):
    help = (
        "Prepare due marketing posts, send consented saved-cart reminders, "
        "and process back-in-stock or price-drop alerts."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show due work without changing records or sending email.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum reminder or alert records processed per category.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        limit = max(1, options["limit"])
        due_posts = ScheduledPost.objects.filter(
            status=ScheduledPost.STATUS_SCHEDULED,
            scheduled_for__isnull=False,
            scheduled_for__lte=now,
        )

        config = GrowthSettings.load()
        first_cutoff = now - timezone.timedelta(
            hours=config.abandoned_cart_first_delay_hours
        )
        second_cutoff = now - timezone.timedelta(
            hours=config.abandoned_cart_second_delay_hours
        )
        due_first = SavedCart.objects.filter(
            status=SavedCart.STATUS_ACTIVE,
            first_reminder_sent_at__isnull=True,
            last_activity__lte=first_cutoff,
        ).count()
        due_second = SavedCart.objects.filter(
            status=SavedCart.STATUS_ACTIVE,
            first_reminder_sent_at__isnull=False,
            first_reminder_sent_at__lte=second_cutoff,
            second_reminder_sent_at__isnull=True,
        ).count()
        active_alerts = StockAlertSubscription.objects.filter(is_active=True).count()

        if options["dry_run"]:
            self.stdout.write(f"Due scheduled posts: {due_posts.count()}")
            self.stdout.write(f"Due first cart reminders: {due_first}")
            self.stdout.write(f"Due second cart reminders: {due_second}")
            self.stdout.write(f"Active stock/price alerts to evaluate: {active_alerts}")
            return

        posts_updated = due_posts.update(status=ScheduledPost.STATUS_READY)
        carts = process_saved_cart_reminders(limit=limit)
        alerts = process_stock_alerts(limit=limit)
        self.stdout.write(
            self.style.SUCCESS(
                "Growth automation complete — "
                f"posts ready: {posts_updated}; "
                f"first reminders: {carts['first']}; "
                f"second reminders: {carts['second']}; "
                f"product alerts: {alerts['sent']}; "
                f"email errors: {carts['errors'] + alerts['errors']}."
            )
        )
