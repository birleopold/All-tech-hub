"""Role-safe, idempotent job handover and customer account visibility."""
import base64
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from PIL import Image, ImageDraw
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import AuditEvent
from crm.models import Customer
from operations.models import JobCard, JobHandover


@override_settings(SECURE_SSL_REDIRECT=False)
class JobHandoverWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.staff = User.objects.create_superuser(
            username="handover-manager", email="handover@example.com", password="pw"
        )
        cls.unprivileged = User.objects.create_user(
            username="handover-helper", is_staff=True, password="pw"
        )
        cls.customer_user = User.objects.create_user(
            username="handover-customer", password="pw"
        )
        cls.other_user = User.objects.create_user(
            username="handover-unrelated", password="pw"
        )
        cls.customer = Customer.objects.create(
            name="Example customer", email="handover-customer@example.com",
            user=cls.customer_user,
        )
        cls.job = JobCard.objects.create(
            customer=cls.customer, title="Laptop repair", status=JobCard.STATUS_INTAKE
        )

    def setUp(self):
        self.media = TemporaryDirectory(prefix="handover-tests-")
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)

    @staticmethod
    def _drawn_signature():
        image = Image.new("RGB", (400, 130), "white")
        draw = ImageDraw.Draw(image)
        draw.line([(30, 75), (90, 45), (175, 85), (290, 60)], fill="black", width=3)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    def _ready(self):
        job = JobCard.objects.get(pk=self.job.pk)
        for status in (
            JobCard.STATUS_DIAGNOSING, JobCard.STATUS_IN_REPAIR,
            JobCard.STATUS_QA, JobCard.STATUS_READY,
        ):
            job.status = status
            job.save()
        return job

    def _submit(self, **values):
        payload = {
            "recipient_name": "Jane Customer",
            "method": JobHandover.METHOD_COLLECTION,
            "note": "Verified with collection slip",
            "confirmed": "on",
            "recipient_consent": "on",
            "signature_data": self._drawn_signature(),
        }
        payload.update(values)
        return self.client.post(
            reverse("staff_job_handover", args=[self.job.pk]), payload
        )

    def test_ready_handover_closes_job_and_is_audited_once(self):
        self._ready()
        self.client.force_login(self.staff)
        response = self._submit()
        self.assertEqual(response.status_code, 302)
        handover = JobHandover.objects.get(job=self.job)
        self.assertEqual(handover.recipient_name, "Jane Customer")
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobCard.STATUS_COMPLETED)
        self.assertEqual(
            AuditEvent.objects.filter(
                verb="job.handover_recorded", target_id=self.job.pk
            ).count(), 1
        )
        second = self._submit(recipient_name="Someone else")
        self.assertEqual(second.status_code, 302)
        self.assertEqual(JobHandover.objects.filter(job=self.job).count(), 1)
        self.assertEqual(
            JobHandover.objects.get(job=self.job).recipient_name, "Jane Customer"
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                verb="job.handover_recorded", target_id=self.job.pk
            ).count(), 1
        )

    def test_confirmation_and_ready_status_are_required(self):
        self.client.force_login(self.staff)
        self.assertEqual(self._submit().status_code, 302)
        self.assertFalse(JobHandover.objects.filter(job=self.job).exists())
        self._ready()
        self.assertEqual(self._submit(confirmed="").status_code, 302)
        self.assertFalse(JobHandover.objects.filter(job=self.job).exists())
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobCard.STATUS_READY)

    def test_permission_and_customer_ownership(self):
        self._ready()
        self.client.force_login(self.unprivileged)
        self.assertEqual(self._submit().status_code, 404)
        self.assertFalse(JobHandover.objects.filter(job=self.job).exists())
        self.client.force_login(self.staff)
        detail = self.client.get(reverse("staff_job_detail", args=[self.job.pk]))
        self.assertContains(detail, "Save signed handover")
        self._submit()
        self.client.force_login(self.customer_user)
        owned = self.client.get(reverse("portal_job_detail", args=[self.job.pk]))
        self.assertContains(owned, "Collection or delivery confirmed")
        self.assertContains(owned, "Jane Customer")
        self.client.force_login(self.other_user)
        other = self.client.get(reverse("portal_job_detail", args=[self.job.pk]))
        self.assertNotEqual(other.status_code, 200)
