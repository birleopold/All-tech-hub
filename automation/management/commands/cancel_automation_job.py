from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from automation.models import AutomationJob, PostChannelDelivery
from automation.services import update_plan_status
from core.audit import log_audit_event


class Command(BaseCommand):
    help = "Cancel one queued, retrying, running or failed automation job without deleting its audit history."

    def add_arguments(self, parser):
        parser.add_argument("idempotency_key")
        parser.add_argument(
            "--reason",
            required=True,
            help="Operational reason for abandoning this job.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        key = options["idempotency_key"].strip()
        reason = options["reason"].strip()
        if not key or not reason:
            raise CommandError("An idempotency key and cancellation reason are required.")

        job = AutomationJob.objects.select_for_update().filter(
            idempotency_key=key
        ).first()
        if job is None:
            raise CommandError("Automation job was not found.")
        if job.status == AutomationJob.STATUS_SUCCEEDED:
            raise CommandError("A succeeded automation job cannot be cancelled.")
        if job.status == AutomationJob.STATUS_CANCELLED:
            self.stdout.write("Automation job is already cancelled.")
            return

        now = timezone.now()
        previous_status = job.status
        job.status = AutomationJob.STATUS_CANCELLED
        job.completed_at = now
        job.locked_at = None
        job.locked_by = ""
        job.last_error = f"Cancelled: {reason}"[:4000]
        job.save()

        if job.delivery_id:
            delivery = PostChannelDelivery.objects.select_for_update().get(
                pk=job.delivery_id
            )
            if delivery.status != PostChannelDelivery.STATUS_PUBLISHED:
                delivery.method = PostChannelDelivery.METHOD_MANUAL
                delivery.status = PostChannelDelivery.STATUS_MANUAL
                delivery.next_attempt_at = None
                delivery.last_error = f"Automatic delivery cancelled: {reason}"[:2000]
                delivery.save()
                update_plan_status(delivery.plan)

        log_audit_event(
            actor=None,
            verb="automation.job_cancelled",
            summary=(
                f"Automation job {key} cancelled from {previous_status}: "
                f"{reason[:300]}"
            ),
            target=job,
        )
        self.stdout.write(self.style.SUCCESS(f"Automation job cancelled: {key}."))
