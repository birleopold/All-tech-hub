import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from reports.conversion import conversion_summary


class Command(BaseCommand):
    help = "Audit order conversion, saved-cart recovery and customer email health."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
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
            help="Exit with failure for failed emails or an enabled non-delivering backend.",
        )

    def handle(self, *args, **options):
        summary = conversion_summary(options["days"])
        if options["json"]:
            self.stdout.write(
                json.dumps(
                    summary,
                    default=lambda value: str(value)
                    if isinstance(value, Decimal)
                    else value.isoformat(),
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            self.stdout.write(f"Conversion lifecycle audit — {summary['days']} days")
            self.stdout.write(f"Orders: {summary['order_count']}")
            self.stdout.write(f"Revenue: {summary['revenue']}")
            self.stdout.write(
                f"Saved carts recovered: {summary['saved_cart_recovered']} "
                f"({summary['saved_cart_recovery_rate']}%)"
            )
            self.stdout.write(
                f"Recovered revenue: {summary['recovered_revenue']}"
            )
            self.stdout.write(
                f"Checkout conversion proxy: {summary['checkout_conversion_proxy']}%"
            )
            self.stdout.write(
                "Customer order emails: "
                f"{'enabled' if summary['order_emails_enabled'] else 'disabled'}; "
                f"delivery backend ready: {summary['email_delivery_ready']}"
            )
            self.stdout.write(
                f"Failed order emails: {summary['failed_order_emails']}"
            )
            self.stdout.write(
                "Orders missing a sent confirmation record: "
                f"{summary['missing_confirmation_emails']}"
            )
            self.stdout.write(
                f"Pending orders older than 24h: {summary['pending_older_than_24h']}"
            )

        if not options["strict"]:
            return
        failures = []
        if summary["order_emails_enabled"] and not summary["email_delivery_ready"]:
            failures.append(
                "customer order emails are enabled but the configured mail backend does not deliver"
            )
        if summary["failed_order_emails"]:
            failures.append(
                f"{summary['failed_order_emails']} customer order email(s) remain failed"
            )
        if failures:
            raise CommandError("; ".join(failures) + ".")
