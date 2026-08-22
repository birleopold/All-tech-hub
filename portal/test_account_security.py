from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.models import Customer


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CustomerAccountSecurityTests(TestCase):
    def test_existing_customer_is_linked_only_after_email_verification(self):
        customer = Customer.objects.create(
            name="Established customer", email="buyer@example.com"
        )
        response = self.client.post(
            reverse("portal_signup"),
            {
                "username": "verified-buyer",
                "email": "BUYER@example.com",
                "full_name": "Different submitted name",
                "phone": "0700000000",
                "company_name": "",
                "password1": "Verified-buyer-password-2026!",
                "password2": "Verified-buyer-password-2026!",
            },
        )

        self.assertRedirects(response, reverse("portal_login"))
        customer.refresh_from_db()
        user = get_user_model().objects.get(username="verified-buyer")
        self.assertFalse(user.is_active)
        self.assertIsNone(customer.user_id)
        self.assertEqual(customer.name, "Established customer")
        self.assertEqual(len(mail.outbox), 1)

        verification_url = next(
            line for line in mail.outbox[0].body.splitlines() if line.startswith("http")
        )
        response = self.client.get(urlsplit(verification_url).path)
        self.assertRedirects(response, reverse("portal_home"))
        customer.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(customer.user_id, user.pk)
        self.assertTrue(user.is_active)

        self.client.logout()
        replay = self.client.get(urlsplit(verification_url).path)
        self.assertRedirects(replay, reverse("portal_login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_customer_login_rejects_staff_accounts(self):
        user = get_user_model().objects.create_user(
            username="staff-only", password="staff-password-2026", is_staff=True
        )
        response = self.client.post(
            reverse("portal_login"),
            {"username": user.username, "password": "staff-password-2026"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_customer_password_reset_does_not_email_staff_accounts(self):
        get_user_model().objects.create_user(
            username="staff-reset",
            email="staff@example.com",
            password="staff-password-2026",
            is_staff=True,
        )
        response = self.client.post(
            reverse("portal_password_reset"), {"email": "staff@example.com"}
        )
        self.assertRedirects(response, reverse("portal_password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(DEBUG=False)
    def test_production_registration_refuses_non_delivery_email_backends(self):
        response = self.client.post(
            reverse("portal_signup"),
            {
                "username": "blocked-delivery",
                "email": "blocked@example.com",
                "full_name": "Blocked customer",
                "phone": "",
                "company_name": "",
                "password1": "Blocked-customer-password-2026!",
                "password2": "Blocked-customer-password-2026!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            get_user_model().objects.filter(username="blocked-delivery").exists()
        )
        self.assertEqual(len(mail.outbox), 0)
