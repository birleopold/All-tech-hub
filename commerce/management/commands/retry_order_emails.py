from django.core.management.base import BaseCommand

from commerce.customer_messages import retry_failed_order_emails


class Command(BaseCommand):
    help = "Retry failed customer order confirmation and status emails."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum failed messages to retry; capped at 500.",
        )

    def handle(self, *args, **options):
        result = retry_failed_order_emails(limit=max(1, options["limit"]))
        self.stdout.write(
            self.style.SUCCESS(
                "Order email retry complete — "
                f"processed: {result['processed']}; sent: {result['sent']}; "
                f"still failed: {result['failed']}."
            )
        )
