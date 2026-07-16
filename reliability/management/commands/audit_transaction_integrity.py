from __future__ import annotations

import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Prefetch
from django.utils import timezone

from commerce.models import Order
from reliability.models import OrderReservation, PaymentAttempt


class Command(BaseCommand):
    help = "Audit order, reservation, payment and cancellation invariants without changing data."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json")
        parser.add_argument(
            "--fail-on-warning",
            action="store_true",
            help="Return a failing exit code for warnings as well as errors.",
        )
        parser.add_argument(
            "--sample-limit",
            type=int,
            default=20,
            help="Maximum order references shown for each finding.",
        )

    def handle(self, *args, **options):
        sample_limit = max(1, min(int(options["sample_limit"] or 20), 100))
        findings: list[dict] = []

        def add_finding(code: str, severity: str, detail: str, references):
            refs = list(dict.fromkeys(str(ref) for ref in references if ref))
            if not refs:
                return
            findings.append(
                {
                    "code": code,
                    "severity": severity,
                    "detail": detail,
                    "count": len(refs),
                    "references": refs[:sample_limit],
                }
            )

        pending_without_reservation = Order.objects.filter(
            status=Order.STATUS_PENDING,
            stock_reservation__isnull=True,
        ).values_list("reference", flat=True)
        add_finding(
            "pending_without_reservation",
            "warning",
            "Pending orders are not covered by the new reservation lifecycle. They may be legacy records.",
            pending_without_reservation,
        )

        reserved_on_nonpending = OrderReservation.objects.filter(
            status=OrderReservation.STATUS_RESERVED,
        ).exclude(order__status=Order.STATUS_PENDING)
        add_finding(
            "reserved_on_nonpending_order",
            "error",
            "Reserved stock is attached to an order that has already advanced or closed.",
            reserved_on_nonpending.values_list("order__reference", flat=True),
        )

        closed_on_active_order = OrderReservation.objects.filter(
            status__in=[
                OrderReservation.STATUS_RELEASED,
                OrderReservation.STATUS_EXPIRED,
            ]
        ).exclude(order__status=Order.STATUS_CANCELLED)
        add_finding(
            "closed_reservation_on_active_order",
            "error",
            "A released or expired reservation is attached to an order that is not cancelled.",
            closed_on_active_order.values_list("order__reference", flat=True),
        )

        committed_on_cancelled = OrderReservation.objects.filter(
            status=OrderReservation.STATUS_COMMITTED,
            order__status=Order.STATUS_CANCELLED,
        )
        add_finding(
            "committed_reservation_on_cancelled_order",
            "error",
            "A cancelled order still has a committed stock reservation.",
            committed_on_cancelled.values_list("order__reference", flat=True),
        )

        overdue_reservations = OrderReservation.objects.filter(
            status=OrderReservation.STATUS_RESERVED,
            expires_at__lt=timezone.now(),
        )
        add_finding(
            "overdue_reservation",
            "error",
            "A reservation has passed its expiry time and should have been processed by the timer.",
            overdue_reservations.values_list("order__reference", flat=True),
        )

        cancelled_without_restoration = Order.objects.filter(
            status=Order.STATUS_CANCELLED,
            stock_reservation__isnull=False,
            stock_restoration__isnull=True,
        ).values_list("reference", flat=True)
        add_finding(
            "cancelled_without_stock_restoration",
            "error",
            "A reservation-aware cancelled order has no one-time stock restoration record.",
            cancelled_without_restoration,
        )

        cancelled_with_live_payments = Order.objects.filter(
            status=Order.STATUS_CANCELLED,
            payment_attempts__status__in=[
                PaymentAttempt.STATUS_CREATED,
                PaymentAttempt.STATUS_PENDING,
                PaymentAttempt.STATUS_AUTHORISED,
                PaymentAttempt.STATUS_PAID,
                PaymentAttempt.STATUS_PARTIALLY_REFUNDED,
                PaymentAttempt.STATUS_DISPUTED,
            ],
        ).distinct()
        add_finding(
            "cancelled_with_live_payment",
            "error",
            "A cancelled order still has an open or unsettled payment attempt.",
            cancelled_with_live_payments.values_list("reference", flat=True),
        )

        counted_attempts = PaymentAttempt.objects.filter(
            status__in=[
                PaymentAttempt.STATUS_PAID,
                PaymentAttempt.STATUS_PARTIALLY_REFUNDED,
            ]
        ).prefetch_related("refunds")
        orders = Order.objects.prefetch_related(
            Prefetch(
                "payment_attempts",
                queryset=counted_attempts,
                to_attr="counted_payment_attempts",
            )
        ).only("id", "reference", "total")
        overpaid = []
        for order in orders.iterator(chunk_size=500):
            paid_total = Decimal("0")
            for attempt in order.counted_payment_attempts:
                refunded = sum(
                    (refund.amount for refund in attempt.refunds.all()),
                    Decimal("0"),
                )
                paid_total += max(Decimal("0"), attempt.amount - refunded)
            if paid_total.quantize(Decimal("0.01")) > order.total:
                overpaid.append(order.reference)
        add_finding(
            "order_overpaid",
            "error",
            "Net successful payment attempts exceed the order total.",
            overpaid,
        )

        severity_counts = {
            "error": sum(item["count"] for item in findings if item["severity"] == "error"),
            "warning": sum(
                item["count"] for item in findings if item["severity"] == "warning"
            ),
        }
        payload = {
            "status": "error" if severity_counts["error"] else "ok",
            "audited_at": timezone.now().isoformat(),
            "severity_counts": severity_counts,
            "findings": findings,
        }

        if options["as_json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True))
        elif not findings:
            self.stdout.write(self.style.SUCCESS("Transaction integrity audit passed."))
        else:
            for finding in findings:
                style = self.style.ERROR if finding["severity"] == "error" else self.style.WARNING
                refs = ", ".join(finding["references"])
                self.stdout.write(
                    style(
                        f"{finding['severity'].upper()} {finding['code']} "
                        f"({finding['count']}): {finding['detail']} [{refs}]"
                    )
                )

        should_fail = severity_counts["error"] > 0 or (
            options["fail_on_warning"] and severity_counts["warning"] > 0
        )
        if should_fail:
            raise CommandError(
                "Transaction integrity audit found "
                f"{severity_counts['error']} error(s) and "
                f"{severity_counts['warning']} warning(s)."
            )
