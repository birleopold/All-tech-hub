from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from automation.models import AutomationJob


class AutomationHealthTests(TestCase):
    def make_job(self, *, key="job-1", status=AutomationJob.STATUS_QUEUED):
        now = timezone.now()
        return AutomationJob.objects.create(
            idempotency_key=key,
            job_type=AutomationJob.TYPE_SAVED_CART_EMAIL,
            status=status,
            payload={"saved_cart_id": 1, "reminder_number": 1},
            scheduled_for=now,
            next_attempt_at=now,
        )

    def test_fresh_queue_passes(self):
        self.make_job()
        call_command("check_automation_health")

    def test_old_queue_fails(self):
        job = self.make_job()
        AutomationJob.objects.filter(pk=job.pk).update(
            next_attempt_at=timezone.now() - timedelta(minutes=60)
        )

        with self.assertRaises(CommandError):
            call_command("check_automation_health", max_queued_age_minutes=30)

    def test_permanent_failure_can_be_reported_without_failing(self):
        self.make_job(status=AutomationJob.STATUS_FAILED)
        call_command("check_automation_health", allow_failed=True)
