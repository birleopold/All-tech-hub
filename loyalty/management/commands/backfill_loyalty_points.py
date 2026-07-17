from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from commerce.models import Order
from loyalty.models import LoyaltyTransaction
from loyalty.services import award_completed_order_points


class Command(BaseCommand):
    help = "Award loyalty points for eligible historical completed orders exactly once."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        if not options["dry_run"] and not getattr(settings, "LOYALTY_POINTS_ENABLED", False):
            raise CommandError(
                "Loyalty points are disabled. Set ALLTECH_LOYALTY_POINTS_ENABLED=1 only after approving the earning rules."
            )
        awarded_order_ids = LoyaltyTransaction.objects.filter(
            idempotency_key__startswith="order:",
            kind=LoyaltyTransaction.KIND_EARN,
        ).values_list("order_reference", flat=True)
        queryset = (
            Order.objects.filter(
                status__in=[Order.STATUS_DELIVERED, Order.STATUS_FULFILLED],
            )
            .exclude(reference__in=awarded_order_ids)
            .exclude(lines__returns__isnull=False)
            .distinct()
            .order_by("placed_at", "id")
        )
        limit = max(0, int(options["limit"] or 0))
        if limit:
            queryset = queryset[:limit]
        orders = list(queryset)
        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run: {len(orders)} completed, non-returned order(s) are eligible for loyalty point review."
                )
            )
            return

        awarded = skipped = 0
        for order in orders:
            row = award_completed_order_points(order)
            if row is None:
                skipped += 1
            else:
                awarded += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Loyalty backfill complete — eligible: {len(orders)}; awarded: {awarded}; skipped: {skipped}."
            )
        )
