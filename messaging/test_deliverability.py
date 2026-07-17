from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from automation.models import AutomationJob
from automation.worker import process_controlled_automation_jobs
from growth.models import SavedCart
from messaging.deliverability import (
    DeliverabilityError,
    active_suppression,
    record_delivery_event,
    release_suppression,
    upsert_suppression,
)
from messaging.forms import ManualEmailSuppressionForm
from messaging.models import EmailDeliveryEvent, EmailSuppression, OutboundEmail
from messaging.reporting import email_deliverability_findings
from messaging.utils import retry_outbound_email, send_outbound_email


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@leosoftug.com",
    EMAIL_SOFT_BOUNCE_SUPPRESSION_THRESHOLD=3,
    EMAIL_SOFT_BOUNCE_WINDOW_DAYS=30,
)
class EmailDeliverabilityTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.manager = user_model.objects.create_user(
            username="delivery-manager",
            password="strong-test-password",
            is_staff=True,
        )
        permissions = Permission.objects.filter(
            content_type__app_label="messaging",
            codename__in=[
                "view_emailsuppression",
                "change_emailsuppression",
                "view_outboundemail",
                "change_outboundemail",
            ],
        )
        self.manager.user_permissions.add(*permissions)
        self.now = timezone.now()

    def send_log(
        self,
        email="customer@example.com",
        *,
        category=OutboundEmail.CATEGORY_MARKETING,
        key=None,
    ):
        return send_outbound_email(
            to_email=email,
            subject="Test message",
            body="Test body",
            created_by=self.manager,
            category=category,
            idempotency_key=key,
        )

    def event(self, log, event_id, event_type, *, occurred_at=None, email=None):
        return record_delivery_event(
            {
                "event_id": event_id,
                "event_type": event_type,
                "tracking_token": str(log.tracking_token),
                "email": email or log.normalized_to_email,
                "provider": "test-provider",
                "provider_message_id": f"provider-{log.pk}",
                "occurred_at": (occurred_at or timezone.now()).isoformat(),
                "metadata": {"diagnostic": f"Test {event_type}"},
            }
        )

    def test_hard_bounce_blocks_all_email(self):
        log = self.send_log(category=OutboundEmail.CATEGORY_TRANSACTIONAL)
        self.event(log, "bounce-1", EmailDeliveryEvent.TYPE_HARD_BOUNCE)
        log.refresh_from_db()
        suppression = EmailSuppression.objects.get(email_address=log.to_email)
        self.assertEqual(log.status, OutboundEmail.STATUS_BOUNCED)
        self.assertEqual(suppression.scope, EmailSuppression.SCOPE_ALL)
        self.assertIsNotNone(
            active_suppression(log.to_email, OutboundEmail.CATEGORY_TRANSACTIONAL)
        )

    def test_complaint_blocks_marketing_but_not_transactional(self):
        marketing = self.send_log(email="complaint@example.com")
        self.event(marketing, "complaint-1", EmailDeliveryEvent.TYPE_COMPLAINT)
        suppression = EmailSuppression.objects.get(email_address=marketing.to_email)
        self.assertEqual(suppression.scope, EmailSuppression.SCOPE_MARKETING)

        before = len(mail.outbox)
        blocked = self.send_log(email=marketing.to_email, key="blocked-marketing")
        transactional = self.send_log(
            email=marketing.to_email,
            category=OutboundEmail.CATEGORY_TRANSACTIONAL,
            key="allowed-transactional",
        )
        self.assertEqual(blocked.status, OutboundEmail.STATUS_SUPPRESSED)
        self.assertEqual(transactional.status, OutboundEmail.STATUS_SENT)
        self.assertEqual(len(mail.outbox), before + 1)

    def test_repeated_soft_bounces_create_all_email_suppression(self):
        log = self.send_log(email="soft@example.com")
        for index in range(3):
            self.event(
                log,
                f"soft-{index}",
                EmailDeliveryEvent.TYPE_SOFT_BOUNCE,
                occurred_at=self.now + timedelta(minutes=index),
            )
        suppression = EmailSuppression.objects.get(email_address=log.to_email)
        self.assertEqual(
            suppression.reason,
            EmailSuppression.REASON_REPEATED_SOFT_BOUNCE,
        )
        self.assertEqual(suppression.scope, EmailSuppression.SCOPE_ALL)

    def test_duplicate_provider_event_is_idempotent(self):
        log = self.send_log()
        first, created_first = self.event(
            log,
            "delivery-duplicate",
            EmailDeliveryEvent.TYPE_DELIVERED,
        )
        second, created_second = self.event(
            log,
            "delivery-duplicate",
            EmailDeliveryEvent.TYPE_DELIVERED,
        )
        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.pk, second.pk)

    def test_late_acceptance_does_not_overwrite_hard_bounce(self):
        log = self.send_log()
        bounce_time = self.now + timedelta(minutes=2)
        self.event(
            log,
            "terminal-bounce",
            EmailDeliveryEvent.TYPE_HARD_BOUNCE,
            occurred_at=bounce_time,
        )
        self.event(
            log,
            "late-accepted",
            EmailDeliveryEvent.TYPE_ACCEPTED,
            occurred_at=self.now,
        )
        log.refresh_from_db()
        self.assertEqual(log.status, OutboundEmail.STATUS_BOUNCED)
        self.assertEqual(log.last_event_at, bounce_time)

    def test_event_email_must_match_outbound_record(self):
        log = self.send_log()
        with self.assertRaisesMessage(DeliverabilityError, "does not match"):
            self.event(
                log,
                "wrong-email",
                EmailDeliveryEvent.TYPE_DELIVERED,
                email="other@example.com",
            )

    def test_idempotency_key_reuses_one_accepted_email(self):
        first = self.send_log(key="same-message")
        second = self.send_log(key="same-message")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(OutboundEmail.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_suppressed_send_never_reaches_email_backend(self):
        upsert_suppression(
            email_address="blocked@example.com",
            reason=EmailSuppression.REASON_MANUAL,
            scope=EmailSuppression.SCOPE_ALL,
            source=EmailSuppression.SOURCE_STAFF,
            actor=self.manager,
            details={"note": "Verified invalid address"},
        )
        log = self.send_log(email="blocked@example.com")
        self.assertEqual(log.status, OutboundEmail.STATUS_SUPPRESSED)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(
            log.delivery_events.filter(
                event_type=EmailDeliveryEvent.TYPE_SUPPRESSED
            ).exists()
        )

    def test_retry_rechecks_active_suppression(self):
        log = OutboundEmail.objects.create(
            to_email="retry@example.com",
            category=OutboundEmail.CATEGORY_TRANSACTIONAL,
            subject="Retry",
            body="Body",
            status=OutboundEmail.STATUS_FAILED,
            error="Temporary SMTP error",
        )
        upsert_suppression(
            email_address=log.to_email,
            reason=EmailSuppression.REASON_HARD_BOUNCE,
            scope=EmailSuppression.SCOPE_ALL,
            source=EmailSuppression.SOURCE_PROVIDER,
        )
        retry_outbound_email(log)
        log.refresh_from_db()
        self.assertEqual(log.status, OutboundEmail.STATUS_SUPPRESSED)
        self.assertEqual(len(mail.outbox), 0)

    def test_suppression_release_preserves_review_reason(self):
        suppression = upsert_suppression(
            email_address="release@example.com",
            reason=EmailSuppression.REASON_MANUAL,
            scope=EmailSuppression.SCOPE_ALL,
            source=EmailSuppression.SOURCE_STAFF,
            actor=self.manager,
        )
        release_suppression(
            suppression,
            user=self.manager,
            reason="Customer confirmed the corrected address.",
        )
        suppression.refresh_from_db()
        self.assertFalse(suppression.is_active)
        self.assertEqual(suppression.released_by, self.manager)
        self.assertIn("corrected", suppression.release_reason)

    def test_manual_suppression_form_requires_exact_phrase(self):
        form = ManualEmailSuppressionForm(
            {
                "email_address": "Case@Example.com",
                "scope": EmailSuppression.SCOPE_ALL,
                "reason": EmailSuppression.REASON_MANUAL,
                "note": "Verified invalid customer address.",
                "confirmation": "SUPPRESS case@example.com",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        invalid = ManualEmailSuppressionForm(
            {
                "email_address": "case@example.com",
                "scope": EmailSuppression.SCOPE_ALL,
                "reason": EmailSuppression.REASON_MANUAL,
                "note": "Verified invalid customer address.",
                "confirmation": "SUPPRESS",
            }
        )
        self.assertFalse(invalid.is_valid())

    def test_deliverability_dashboard_requires_dedicated_permission(self):
        viewer = get_user_model().objects.create_user(
            username="email-viewer",
            password="strong-test-password",
            is_staff=True,
        )
        self.client.force_login(viewer)
        self.assertEqual(
            self.client.get(reverse("staff_email_deliverability")).status_code,
            403,
        )
        self.client.force_login(self.manager)
        response = self.client.get(reverse("staff_email_deliverability"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email deliverability center")
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    def test_suppressed_saved_cart_job_finishes_as_safe_skip(self):
        saved = SavedCart.objects.create(
            session_key="delivery-test-session",
            customer_name="Test Customer",
            email="cart-blocked@example.com",
            cart_data={},
            subtotal="10000.00",
            last_activity=self.now - timedelta(hours=3),
        )
        upsert_suppression(
            email_address=saved.email,
            reason=EmailSuppression.REASON_COMPLAINT,
            scope=EmailSuppression.SCOPE_MARKETING,
            source=EmailSuppression.SOURCE_PROVIDER,
        )
        job = AutomationJob.objects.create(
            idempotency_key=f"saved-cart:{saved.pk}:test",
            job_type=AutomationJob.TYPE_SAVED_CART_EMAIL,
            payload={"saved_cart_id": saved.pk, "reminder_number": 1},
            scheduled_for=self.now,
            next_attempt_at=self.now,
        )
        result = process_controlled_automation_jobs(limit=5, worker_id="test-worker")
        job.refresh_from_db()
        saved.refresh_from_db()
        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(job.status, AutomationJob.STATUS_SUCCEEDED)
        self.assertIsNotNone(saved.first_reminder_sent_at)
        self.assertEqual(len(mail.outbox), 0)

    def test_clean_records_pass_strict_findings(self):
        self.send_log(key="clean-ledger")
        findings = email_deliverability_findings()
        self.assertEqual(findings["errors"], 0)
