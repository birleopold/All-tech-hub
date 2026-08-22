from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import StaffTwoFactor
from core.security import STAFF_TWO_FACTOR_SESSION_KEY


@override_settings(REQUIRE_STAFF_2FA=True)
class StaffTwoFactorSessionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="challenge-required",
            password="challenge-password-2026",
            is_staff=True,
            is_superuser=True,
        )
        StaffTwoFactor.objects.create(
            user=self.user, secret="A" * 32, enabled=True
        )
        self.client.force_login(self.user)

    def test_staff_workspace_rejects_session_without_totp_challenge(self):
        response = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_admin_rejects_session_without_totp_challenge(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_enabled_authenticator_setup_does_not_expose_the_existing_secret(self):
        response = self.client.get(reverse("staff_two_factor_setup"))
        self.assertRedirects(response, reverse("login"))

    def test_verified_session_can_access_staff_workspace(self):
        session = self.client.session
        session[STAFF_TWO_FACTOR_SESSION_KEY] = str(self.user.pk)
        session.save()
        response = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(response.status_code, 200)


@override_settings(ENFORCE_STAFF_ROLES=True, REQUIRE_STAFF_2FA=False)
class SensitiveActionPermissionTests(TestCase):
    def test_document_view_permission_cannot_record_payment(self):
        user = get_user_model().objects.create_user(
            username="documents-read-only", password="password-2026", is_staff=True
        )
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="billing", codename="view_commercialdocument"
            )
        )
        self.client.force_login(user)
        response = self.client.post(reverse("staff_document_payment", args=[999999]))
        self.assertEqual(response.status_code, 403)
