from django.core.management.base import BaseCommand, CommandError

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
        try:
            result = retry_failed_order_emails(limit=max(1, options["limit"]))
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Order email retry complete — "
                f"processed: {result['processed']}; sent: {result['sent']}; "
                f"still failed: {result['failed']}."
            )
        )
