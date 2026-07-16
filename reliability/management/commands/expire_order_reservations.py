from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from commerce.fulfillment import transition_order
from commerce.models import Order
from reliability.models import OrderReservation
from reliability.services import close_order_reservation, commit_order_reservation


class Command(BaseCommand):
    help = "Expire due pending-order stock reservations and safely release their stock."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report due reservations without changing orders or stock.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Maximum reservations to inspect in one run.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        limit = max(1, min(int(options["limit"] or 200), 2000))
        due_ids = list(
            OrderReservation.objects.filter(
                status=OrderReservation.STATUS_RESERVED,
                expires_at__lte=now,
            )
            .order_by("expires_at", "id")
            .values_list("pk", flat=True)[:limit]
        )

        if options["dry_run"]:
            self.stdout.write(f"Due reservations: {len(due_ids)}")
            return

        expired = committed = already_closed = failed = 0
        for reservation_id in due_ids:
            try:
                with transaction.atomic():
                    order_id = OrderReservation.objects.values_list(
                        "order_id",
                        flat=True,
                    ).get(pk=reservation_id)
                    order = Order.objects.select_for_update().get(pk=order_id)
                    reservation = OrderReservation.objects.select_for_update().get(
                        pk=reservation_id
                    )
                    if reservation.status != OrderReservation.STATUS_RESERVED:
                        already_closed += 1
                        continue
                    if reservation.expires_at > timezone.now():
                        already_closed += 1
                        continue
                    if order.status == Order.STATUS_PENDING:
                        transition_order(
                            order,
                            Order.STATUS_CANCELLED,
                            actor=None,
                            note=(
                                "Reservation expired before payment or staff confirmation."
                            ),
                        )
                        expired += 1
                    elif order.status == Order.STATUS_CANCELLED:
                        close_order_reservation(
                            order,
                            reason="Reservation expired after order cancellation.",
                            expired=True,
                        )
                        already_closed += 1
                    else:
                        commit_order_reservation(
                            order,
                            reason=(
                                f"Order was already {order.get_status_display()} when "
                                "reservation expiry was checked."
                            ),
                        )
                        committed += 1
            except Exception as exc:
                failed += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"Reservation {reservation_id} could not be processed: {exc}"
                    )
                )

        summary = (
            "Reservation expiry complete — "
            f"expired: {expired}; committed: {committed}; "
            f"already closed: {already_closed}; failed: {failed}."
        )
        if failed:
            raise CommandError(summary)
        self.stdout.write(self.style.SUCCESS(summary))
