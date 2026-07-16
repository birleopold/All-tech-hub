from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.field_encryption import (
    is_protected_secret,
    protect_totp_secret,
    reveal_totp_secret,
)
from core.models import StaffTwoFactor, SupportTicket, TicketComment
from core.totp import generate_secret, token_for
from crm.models import Customer


@override_settings(
    FIELD_ENCRYPTION_KEY="phase-1-test-key-that-is-longer-than-thirty-two-characters",
    PRIVATE_MEDIA_USE_X_ACCEL=False,
)
class PhaseOneSecurityTests(TestCase):
    def setUp(self):
        self.media_dir = TemporaryDirectory()
        self.addCleanup(self.media_dir.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

    def test_totp_secret_round_trip_is_compact_and_encrypted(self):
        secret = generate_secret()
        protected = protect_totp_secret(secret)

        self.assertTrue(is_protected_secret(protected))
        self.assertLessEqual(len(protected), 64)
        self.assertNotEqual(protected, secret)
        self.assertEqual(reveal_totp_secret(protected), secret)

    def test_setup_encrypts_legacy_plaintext_secret(self):
        staff = User.objects.create_user(
            username="phase1-staff",
            password="safe-password-123",
            is_staff=True,
        )
        secret = generate_secret()
        profile = StaffTwoFactor.objects.create(user=staff, secret=secret)
        self.client.force_login(staff)

        response = self.client.get(reverse("staff_two_factor_setup"))
        profile.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(is_protected_secret(profile.secret))
        self.assertContains(response, secret)
        self.assertNotContains(response, profile.secret)

    def test_disabling_2fa_requires_password_and_live_otp(self):
        staff = User.objects.create_user(
            username="secure-staff",
            password="safe-password-123",
            is_staff=True,
        )
        secret = generate_secret()
        profile = StaffTwoFactor.objects.create(
            user=staff,
            secret=protect_totp_secret(secret),
            enabled=True,
        )
        self.client.force_login(staff)

        response = self.client.post(
            reverse("staff_two_factor_disable"),
            {"password": "wrong", "otp": token_for(secret)},
        )
        profile.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(profile.enabled)

        response = self.client.post(
            reverse("staff_two_factor_disable"),
            {"password": "safe-password-123", "otp": token_for(secret)},
        )
        profile.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(profile.enabled)

    def test_service_worker_never_caches_navigation_or_media(self):
        response = self.client.get(reverse("service_worker"))
        body = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('fetch(request, { cache: "no-store" })', body)
        self.assertIn('if (!url.pathname.startsWith("/static/")) return;', body)
        self.assertNotIn('url.pathname.startsWith("/media/")', body)
        self.assertEqual(response["Cache-Control"], "no-cache, no-store, must-revalidate")

    def test_ticket_attachment_requires_staff_or_owning_customer(self):
        staff = User.objects.create_user(
            username="ticket-staff",
            password="safe-password-123",
            is_staff=True,
        )
        customer_user = User.objects.create_user(
            username="ticket-customer",
            password="safe-password-123",
        )
        customer = Customer.objects.create(
            user=customer_user,
            name="Ticket Customer",
            email="ticket@example.com",
        )
        ticket = SupportTicket.objects.create(
            customer=customer,
            subject="Private attachment",
            description="Please keep this file private.",
        )
        comment = TicketComment.objects.create(
            ticket=ticket,
            author=staff,
            body="Protected evidence",
            is_internal=False,
            attachment=SimpleUploadedFile(
                "evidence.txt",
                b"private evidence",
                content_type="text/plain",
            ),
        )

        staff_url = reverse("staff_ticket_attachment", args=[comment.pk])
        portal_url = reverse("portal_ticket_attachment", args=[comment.pk])
        self.assertEqual(self.client.get(staff_url).status_code, 404)

        self.client.force_login(staff)
        staff_response = self.client.get(staff_url)
        self.assertEqual(staff_response.status_code, 200)
        self.assertEqual(staff_response["Cache-Control"], "private, no-store, max-age=0")

        self.client.force_login(customer_user)
        portal_response = self.client.get(portal_url)
        self.assertEqual(portal_response.status_code, 200)

        other_user = User.objects.create_user(
            username="other-customer",
            password="safe-password-123",
        )
        Customer.objects.create(
            user=other_user,
            name="Other Customer",
            email="other@example.com",
        )
        self.client.force_login(other_user)
        self.assertEqual(self.client.get(portal_url).status_code, 404)

        Path(comment.attachment.path).unlink(missing_ok=True)
