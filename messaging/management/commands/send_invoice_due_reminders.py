from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from billing.models import CommercialDocument
from core.models import CompanySettings
from messaging.utils import send_outbound_email


class Command(BaseCommand):
    help = (
        "Email customers about invoices due soon (default: within the next 3 days). "
        "Respects last_payment_reminder_sent to avoid spamming more than once per week per document."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=3,
            help="Include invoices with due_date within this many days from today.",
        )
        parser.add_argument(
            "--min-days-since-reminder",
            type=int,
            default=7,
            help="Skip if a reminder was sent more recently than this many days ago.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print matches without sending email.",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        horizon = today + timedelta(days=int(options["days"]))
        min_gap = timedelta(days=int(options["min_days_since_reminder"]))
        dry = options["dry_run"]
        company = CompanySettings.load()
        now = timezone.now()

        qs = (
            CommercialDocument.objects.filter(
                doc_type=CommercialDocument.TYPE_INVOICE,
                due_date__isnull=False,
                due_date__gte=today,
                due_date__lte=horizon,
            )
            .exclude(
                status__in=(
                    CommercialDocument.STATUS_PAID,
                    CommercialDocument.STATUS_CANCELLED,
                )
            )
            .select_related("customer")
        )

        sent = 0
        for doc in qs:
            if doc.total <= doc.amount_paid:
                continue
            balance = (doc.total - doc.amount_paid).quantize(Decimal("0.01"))
            if balance <= 0:
                continue
            if doc.last_payment_reminder_sent and (
                now - doc.last_payment_reminder_sent < min_gap
            ):
                continue
            to_email = doc.customer.email.strip()
            if not to_email:
                self.stdout.write(self.style.WARNING(f"Skip {doc.number}: no customer email."))
                continue
            subject = f"Reminder: invoice {doc.number} due {doc.due_date}"
            body = (
                f"Dear {doc.customer.name},\n\n"
                f"This is a friendly reminder that invoice {doc.number} for "
                f"{company.currency_code} {doc.total} has a balance of "
                f"{company.currency_code} {balance} with due date {doc.due_date}.\n\n"
                f"If you have already paid, please disregard this message.\n\n"
                f"— {company.company_name}"
            )
            if dry:
                self.stdout.write(f"[dry-run] Would email {to_email}: {subject}")
                sent += 1
                continue
            send_outbound_email(
                to_email=to_email,
                subject=subject,
                body=body,
                created_by=None,
                commercial_document=doc,
            )
            doc.last_payment_reminder_sent = now
            doc.save(update_fields=["last_payment_reminder_sent", "updated_at"])
            sent += 1
            self.stdout.write(self.style.SUCCESS(f"Reminder queued/sent for {doc.number} → {to_email}"))

        self.stdout.write(self.style.SUCCESS(f"Processed {sent} invoice(s)."))
