"""Signed handover: normalised evidence, ownership isolation and safe writes."""
import base64
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image, ImageDraw

from crm.models import Customer
from operations.models import JobCard, JobHandover


@override_settings(SECURE_SSL_REDIRECT=False, PRIVATE_MEDIA_USE_X_ACCEL=False)
class SignedJobHandoverTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="leosoft-signed-handover-")
        self.addCleanup(self.temp.cleanup)
        config = override_settings(MEDIA_ROOT=self.temp.name)
        config.enable()
        self.addCleanup(config.disable)
        User = get_user_model()
        self.staff = User.objects.create_superuser(
            username="signed-admin", email="signed-admin@example.com", password="pw"
        )
        self.customer_user = User.objects.create_user(
            username="signed-owner", password="pw"
        )
        self.other_user = User.objects.create_user(
            username="signed-unrelated", password="pw"
        )
        self.customer = Customer.objects.create(
            name="Signed owner", user=self.customer_user,
            email="signed-owner@example.com",
        )
        self.job = JobCard.objects.create(
            customer=self.customer, title="Laptop repair"
        )
        self.url = reverse("staff_job_handover", args=[self.job.pk])

    @staticmethod
    def picture(format="PNG"):
        image = Image.new("RGB", (500, 140), "white")
        pencil = ImageDraw.Draw(image)
        pencil.line([(25, 80), (92, 50), (160, 95), (280, 65)], fill="black", width=4)
        binary = BytesIO()
        image.save(binary, format=format)
        return binary.getvalue()

    def ready(self):
        for status in (
            JobCard.STATUS_DIAGNOSING, JobCard.STATUS_IN_REPAIR,
            JobCard.STATUS_QA, JobCard.STATUS_READY,
        ):
            self.job.status = status
            self.job.save()

    def submit(self, **changes):
        payload = {
            "recipient_name": "Test recipient",
            "method": JobHandover.METHOD_COLLECTION,
            "recipient_consent": "on",
            "confirmed": "on",
            "signature_data": "data:image/png;base64,"
            + base64.b64encode(self.picture()).decode("ascii"),
        }
        payload.update(changes)
        return self.client.post(self.url, payload)

    def test_touch_signature_creates_normalised_protected_file(self):
        self.ready()
        self.client.force_login(self.staff)
        response = self.submit()
        self.assertEqual(response.status_code, 302)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobCard.STATUS_COMPLETED)
        handover = JobHandover.objects.get(job=self.job)
        self.assertTrue(handover.signature.name.startswith("job_signatures/handover/"))
        self.assertTrue(handover.signature.name.endswith(".png"))
        with handover.signature.open("rb") as signature:
            with Image.open(signature) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (500, 140))
        detail = self.client.get(reverse("staff_job_detail", args=[self.job.pk]))
        self.assertContains(detail, "View protected recipient signature")

    def test_uploaded_jpeg_is_reencoded_png_without_metadata(self):
        self.ready()
        self.client.force_login(self.staff)
        uploaded = SimpleUploadedFile(
            "signature.jpg", self.picture("JPEG"), content_type="image/jpeg"
        )
        self.submit(signature_data="", signature_upload=uploaded)
        handover = JobHandover.objects.get(job=self.job)
        self.assertTrue(handover.signature.name.endswith(".png"))
        with handover.signature.open("rb") as signature:
            self.assertEqual(Image.open(signature).format, "PNG")

    def test_signature_and_consent_are_required(self):
        self.ready()
        self.client.force_login(self.staff)
        for changes in (
            {"signature_data": ""},
            {"recipient_consent": ""},
            {"confirmed": ""},
            {"signature_data": "data:image/png;base64,not-base64"},
            {"signature_data": "data:text/html;base64,PGgxPmJhZDwvaDE+"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.submit(**changes).status_code, 302)
                self.assertFalse(JobHandover.objects.filter(job=self.job).exists())
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobCard.STATUS_READY)

    def test_signature_size_limit_blocks_handover(self):
        self.ready()
        self.client.force_login(self.staff)
        large = SimpleUploadedFile(
            "big.png", b"x" * (512 * 1024 + 1), content_type="image/png"
        )
        self.submit(signature_data="", signature_upload=large)
        self.assertFalse(JobHandover.objects.filter(job=self.job).exists())

    def test_signature_access_requires_staff_or_same_customer(self):
        self.ready()
        self.client.force_login(self.staff)
        self.submit()
        staff_url = reverse("staff_job_handover_signature", args=[self.job.pk])
        portal_url = reverse("portal_job_handover_signature", args=[self.job.pk])
        staff_response = self.client.get(staff_url)
        self.assertEqual(staff_response.status_code, 200)
        self.assertEqual(staff_response["Cache-Control"], "private, no-store, max-age=0")
        self.assertEqual(staff_response["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("X-Accel-Redirect", staff_response)
        self.client.force_login(self.customer_user)
        self.assertEqual(self.client.get(staff_url).status_code, 404)
        portal_response = self.client.get(portal_url)
        self.assertEqual(portal_response.status_code, 200)
        self.assertEqual(portal_response["Content-Type"], "image/png")
        portal_detail = self.client.get(reverse("portal_job_detail", args=[self.job.pk]))
        self.assertContains(portal_detail, "View signed handover acknowledgement")
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(portal_url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(staff_url).status_code, 404)
        self.assertRedirects(self.client.get(portal_url), reverse("portal_login"))

    def test_duplicate_post_retains_original_signature_and_recipient(self):
        self.ready()
        self.client.force_login(self.staff)
        self.submit()
        first = JobHandover.objects.get(job=self.job)
        original = first.signature.name
        self.assertEqual(self.submit(recipient_name="Other").status_code, 302)
        first.refresh_from_db()
        self.assertEqual(first.signature.name, original)
        self.assertEqual(first.recipient_name, "Test recipient")
        self.assertEqual(JobHandover.objects.filter(job=self.job).count(), 1)

    def test_old_handover_can_remain_unsigned_without_fabricating_evidence(self):
        self.ready()
        self.job.status = JobCard.STATUS_COMPLETED
        self.job.save()
        JobHandover.objects.create(
            job=self.job, recipient_name="Old recipient",
            method=JobHandover.METHOD_DELIVERY, recorded_by=self.staff,
        )
        self.client.force_login(self.staff)
        detail = self.client.get(reverse("staff_job_detail", args=[self.job.pk]))
        self.assertContains(detail, "Legacy handover: recipient signature was not captured.")
        self.assertNotContains(detail, "View protected recipient signature")
