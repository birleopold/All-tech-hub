from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from messaging.models import OutboundEmail
from messaging.utils import send_outbound_email


class OutboundEmailTests(TestCase):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_success_is_logged(self):
        user = User.objects.create_user("mailer", password="pw", is_staff=True)
        log = send_outbound_email(
            to_email="person@example.com",
            subject="Hello",
            body="Body",
            created_by=user,
        )
        self.assertEqual(log.status, OutboundEmail.STATUS_SENT)

    @override_settings(EMAIL_BACKEND="does.not.exist.Backend")
    def test_failure_is_logged_instead_of_raised(self):
        log = send_outbound_email(
            to_email="person@example.com",
            subject="Hello",
            body="Body",
            created_by=None,
        )
        self.assertEqual(log.status, OutboundEmail.STATUS_FAILED)
        self.assertTrue(log.error)
