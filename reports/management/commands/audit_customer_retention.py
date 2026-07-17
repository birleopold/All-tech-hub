import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from reports.retention import retention_summary


class Command(BaseCommand):
    help = "Audit repeat sales, verified reviews and warranty follow-up readiness."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Reporting window from 1 to 365 days.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable JSON.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help=(
                "Exit with failure when review emails remain failed or review emails "
                "are enabled with a non-delivering backend."
            ),
        )

    def handle(self, *args, **options):
        summary = retention_summary(options["days"])
        if options["json"]:
            serializable = {
                key: value
                for key, value in summary.items()
                if key not in {"expiring_warranties", "dormant_customers", "top_customers"}
            }
            self.stdout.write(
                json.dumps(
                    serializable,
                    default=lambda value: str(value)
                    if isinstance(value, Decimal)
                    else value.isoformat(),
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            self.stdout.write(f"Customer retention audit — {summary['days']} days")
            self.stdout.write(f"Customers: {summary['unique_customers']}")
            self.stdout.write(
                f"Repeat customers: {summary['repeat_customers']} "
                f"({summary['repeat_customer_rate']}%)"
            )
            self.stdout.write(
                f"Repeat-customer revenue: {summary['repeat_revenue']} "
                f"({summary['repeat_revenue_rate']}%)"
            )
            self.stdout.write(
                f"Verified reviews: {summary['verified_review_count']}"
            )
            self.stdout.write(
                f"Review requests sent/failed: {summary['review_requests_sent']}/"
                f"{summary['review_requests_failed']}"
            )
            self.stdout.write(
                f"Warranties expiring within 30 days: "
                f"{summary['expiring_warranty_count']}"
            )
            self.stdout.write(
                f"Dormant customers (90+ days): {summary['dormant_customer_count']}"
            )

        strict_errors = []
        if summary["review_requests_failed"]:
            strict_errors.append(
                f"{summary['review_requests_failed']} review request email(s) remain failed"
            )
        if summary["review_email_enabled"] and not summary["email_delivery_ready"]:
            strict_errors.append(
                "review emails are enabled while the configured backend cannot deliver"
            )
        if options["strict"] and strict_errors:
            raise CommandError("; ".join(strict_errors))
