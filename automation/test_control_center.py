from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from automation.control import (
    AutomationControlError,
    cancel_open_job,
    finish_automation_run,
    pause_automation,
    replay_failed_job,
    resume_automation,
    start_automation_run,
)
from automation.forms import AutomationPauseForm, AutomationResumeForm
from automation.models import (
    AutomationControl,
    AutomationJob,
    AutomationJobEvent,
    AutomationRun,
)
from automation.reporting import automation_integrity_findings
from automation.services import recover_stale_jobs
from automation.worker import claim_controlled_job, process_controlled_automation_jobs


class AutomationControlCenterTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.manager = user_model.objects.create_user(
            username="automation-manager",
            password="strong-test-password",
            is_staff=True,
        )
        permissions = Permission.objects.filter(
            content_type__app_label="automation",
            codename__in=["view_automationjob", "change_automationjob"],
        )
        self.manager.user_permissions.add(*permissions)
        self.now = timezone.now()

    def create_job(self, *, job_type=AutomationJob.TYPE_STOCK_ALERT_EMAIL, status=None):
        return AutomationJob.objects.create(
            idempotency_key=f"test:{job_type}:{AutomationJob.objects.count() + 1}",
            job_type=job_type,
            status=status or AutomationJob.STATUS_QUEUED,
            payload={"subscription_id": 999999},
            scheduled_for=self.now,
            next_attempt_at=self.now,
            max_attempts=3,
            completed_at=(
                self.now
                if status in {
                    AutomationJob.STATUS_FAILED,
                    AutomationJob.STATUS_CANCELLED,
                    AutomationJob.STATUS_SUCCEEDED,
                }
                else None
            ),
            last_error="Test failure" if status == AutomationJob.STATUS_FAILED else "",
        )

    def test_master_pause_stops_worker_claims(self):
        job = self.create_job()
        pause_automation(
            user=self.manager,
            reason="SMTP incident under review",
        )
        result = process_controlled_automation_jobs(limit=5)
        job.refresh_from_db()
        self.assertTrue(result["paused"])
        self.assertEqual(job.status, AutomationJob.STATUS_QUEUED)
        self.assertTrue(AutomationControl.load().is_paused)

    def test_job_type_pause_skips_only_selected_type(self):
        paused_job = self.create_job(job_type=AutomationJob.TYPE_SAVED_CART_EMAIL)
        available_job = self.create_job(job_type=AutomationJob.TYPE_STOCK_ALERT_EMAIL)
        pause_automation(
            user=self.manager,
            reason="Saved-cart copy is under review",
            job_types=[AutomationJob.TYPE_SAVED_CART_EMAIL],
        )
        claimed = claim_controlled_job("test-worker")
        self.assertEqual(claimed.pk, available_job.pk)
        paused_job.refresh_from_db()
        self.assertEqual(paused_job.status, AutomationJob.STATUS_QUEUED)

    def test_order_notification_types_can_be_paused_individually(self):
        paused_job = self.create_job(
            job_type=AutomationJob.TYPE_ORDER_CONFIRMATION_EMAIL
        )
        available_job = self.create_job(
            job_type=AutomationJob.TYPE_ORDER_STATUS_EMAIL
        )
        pause_automation(
            user=self.manager,
            reason="Order confirmation delivery is under review",
            job_types=[AutomationJob.TYPE_ORDER_CONFIRMATION_EMAIL],
        )
        claimed = claim_controlled_job("test-worker")
        self.assertEqual(claimed.pk, available_job.pk)
        paused_job.refresh_from_db()
        self.assertEqual(paused_job.status, AutomationJob.STATUS_QUEUED)

    def test_resume_clears_master_and_type_pauses(self):
        pause_automation(
            user=self.manager,
            reason="Maintenance",
            job_types=[AutomationJob.TYPE_STOCK_ALERT_EMAIL],
        )
        pause_automation(user=self.manager, reason="Emergency stop")
        resume_automation(user=self.manager)
        control = AutomationControl.load()
        self.assertFalse(control.is_paused)
        self.assertEqual(control.paused_job_types, [])
        self.assertEqual(control.pause_reason, "")

    def test_job_status_transitions_create_append_only_events(self):
        job = self.create_job()
        self.assertTrue(
            job.events.filter(action=AutomationJobEvent.ACTION_QUEUED).exists()
        )
        job.status = AutomationJob.STATUS_RUNNING
        job.locked_at = self.now
        job.locked_by = "test-worker"
        job.save(update_fields=["status", "locked_at", "locked_by", "updated_at"])
        self.assertTrue(
            job.events.filter(action=AutomationJobEvent.ACTION_CLAIMED).exists()
        )

    def test_stale_lock_recovery_is_recorded(self):
        job = self.create_job(status=AutomationJob.STATUS_RUNNING)
        job.attempt_count = 1
        job.locked_at = self.now - timedelta(hours=1)
        job.locked_by = "stale-worker"
        job.save(
            update_fields=[
                "attempt_count",
                "locked_at",
                "locked_by",
                "updated_at",
            ]
        )
        self.assertEqual(recover_stale_jobs(stale_minutes=15), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, AutomationJob.STATUS_RETRY)
        self.assertTrue(
            job.events.filter(action=AutomationJobEvent.ACTION_RECOVERED).exists()
        )

    def test_failed_email_job_can_be_replayed_after_review(self):
        job = self.create_job(status=AutomationJob.STATUS_FAILED)
        replay_failed_job(job, user=self.manager)
        job.refresh_from_db()
        self.assertEqual(job.status, AutomationJob.STATUS_QUEUED)
        self.assertEqual(job.attempt_count, 0)
        self.assertIsNone(job.completed_at)
        self.assertTrue(
            job.events.filter(action=AutomationJobEvent.ACTION_REPLAYED).exists()
        )

    def test_social_post_replay_is_blocked(self):
        job = self.create_job(
            job_type=AutomationJob.TYPE_SOCIAL_POST,
            status=AutomationJob.STATUS_FAILED,
        )
        with self.assertRaisesMessage(AutomationControlError, "Social-post replay is blocked"):
            replay_failed_job(job, user=self.manager)
        job.refresh_from_db()
        self.assertEqual(job.status, AutomationJob.STATUS_FAILED)
        self.assertTrue(
            job.events.filter(action=AutomationJobEvent.ACTION_BLOCKED).exists()
        )

    def test_reviewed_failed_job_can_be_closed(self):
        call_command("run_growth_automation", "--dry-run", "--limit", "5")
        job = self.create_job(
            job_type=AutomationJob.TYPE_SOCIAL_POST,
            status=AutomationJob.STATUS_FAILED,
        )
        self.assertEqual(automation_integrity_findings()["dead_letter_jobs"], 1)
        cancel_open_job(
            job,
            user=self.manager,
            reason="Verified no external post exists; scheduled post will be rebuilt.",
        )
        job.refresh_from_db()
        self.assertEqual(job.status, AutomationJob.STATUS_CANCELLED)
        self.assertEqual(automation_integrity_findings()["dead_letter_jobs"], 0)
        self.assertTrue(
            job.events.filter(
                action=AutomationJobEvent.ACTION_CANCELLED,
                actor=self.manager,
            ).exists()
        )

    def test_running_job_cannot_be_cancelled(self):
        job = self.create_job(status=AutomationJob.STATUS_RUNNING)
        job.locked_at = self.now
        job.locked_by = "test-worker"
        job.save(update_fields=["locked_at", "locked_by", "updated_at"])
        with self.assertRaisesMessage(AutomationControlError, "cannot be cancelled"):
            cancel_open_job(job, user=self.manager)

    def test_confirmation_forms_require_exact_phrases(self):
        invalid_pause = AutomationPauseForm(
            {"scope": "all", "reason": "Test", "confirmation": "pause"}
        )
        self.assertFalse(invalid_pause.is_valid())
        valid_pause = AutomationPauseForm(
            {
                "scope": "all",
                "reason": "Test",
                "confirmation": "PAUSE AUTOMATION",
            }
        )
        self.assertTrue(valid_pause.is_valid(), valid_pause.errors)
        valid_resume = AutomationResumeForm(
            {"scope": "all", "confirmation": "RESUME AUTOMATION"}
        )
        self.assertTrue(valid_resume.is_valid(), valid_resume.errors)

    def test_control_center_requires_automation_permission(self):
        viewer = get_user_model().objects.create_user(
            username="automation-viewer",
            password="strong-test-password",
            is_staff=True,
        )
        self.client.force_login(viewer)
        self.assertEqual(
            self.client.get(reverse("staff_automation_control")).status_code,
            403,
        )

    def test_control_center_is_private(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("staff_automation_control"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Automation control center")
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertIn("noindex", response.headers["X-Robots-Tag"])

    def test_dry_run_records_fresh_heartbeat(self):
        call_command("run_growth_automation", "--dry-run", "--limit", "5")
        control = AutomationControl.load()
        run = AutomationRun.objects.latest("id")
        self.assertIsNotNone(control.last_heartbeat_at)
        self.assertEqual(control.last_run_status, AutomationControl.RUN_DRY)
        self.assertEqual(run.status, AutomationRun.STATUS_DRY)
        self.assertEqual(automation_integrity_findings()["heartbeat_error"], 0)

    def test_failed_run_increments_consecutive_failures(self):
        run = start_automation_run(source=AutomationRun.SOURCE_MANUAL)
        finish_automation_run(
            run,
            status=AutomationRun.STATUS_FAILED,
            error="Worker test failure",
        )
        control = AutomationControl.load()
        self.assertEqual(control.consecutive_failures, 1)
        self.assertEqual(control.last_run_status, AutomationControl.RUN_FAILED)

    def test_integrity_audit_detects_dead_letter(self):
        call_command("run_growth_automation", "--dry-run", "--limit", "5")
        self.create_job(status=AutomationJob.STATUS_FAILED)
        findings = automation_integrity_findings()
        self.assertEqual(findings["dead_letter_jobs"], 1)
        self.assertGreater(findings["errors"], 0)
