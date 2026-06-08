from __future__ import annotations

from django.core.management.base import BaseCommand

from billing.pdf import render_commercial_pdf
from messaging.models import OutboundEmail
from messaging.utils import retry_outbound_email
from operations.pdf import render_jobcard_pdf


class Command(BaseCommand):
    help = "Retry queued/failed outbound emails."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument(
            "--status",
            choices=[OutboundEmail.STATUS_QUEUED, OutboundEmail.STATUS_FAILED],
            default=OutboundEmail.STATUS_FAILED,
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        status = options["status"]

        qs = (
            OutboundEmail.objects.select_related("commercial_document", "job_card")
            .filter(status=status)
            .order_by("created_at")[:limit]
        )
        count = 0
        for log in qs:
            attachment_name = None
            attachment_bytes = None
            if log.commercial_document_id:
                attachment_name = f"{log.commercial_document.number}.pdf"
                attachment_bytes = render_commercial_pdf(log.commercial_document)
            elif log.job_card_id:
                attachment_name = f"{log.job_card.number}.pdf"
                attachment_bytes = render_jobcard_pdf(log.job_card)
            retry_outbound_email(
                log,
                attachment_name=attachment_name,
                attachment_bytes=attachment_bytes,
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Retried {count} emails ({status})."))

