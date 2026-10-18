"""End-to-end server protection for manually replayed offline field notes."""
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.models import Customer
from operations.models import JobCard, JobNote


@override_settings(SECURE_SSL_REDIRECT=False)
class OfflineFieldNoteTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.technician = User.objects.create_user(
            username="field-tech", password="pw", is_staff=True,
        )
        self.technician.user_permissions.add(
            Permission.objects.get(codename="add_jobnote")
        )
        self.no_permission = User.objects.create_user(
            username="field-observer", password="pw", is_staff=True,
        )
        self.customer_user = User.objects.create_user(
            username="field-customer", password="pw",
        )
        customer = Customer.objects.create(
            name="Field customer", user=self.customer_user,
        )
        self.job = JobCard.objects.create(customer=customer, title="Field visit")
        self.url = reverse("staff_offline_job_note_sync", args=[self.job.pk])
        self.key = uuid4()

    def submit(self, **changes):
        payload = {
            "body": "Checked and documented the router ports.",
            "operation_id": str(self.key),
            "base_version": self.job.updated_at.isoformat(),
            "is_internal": "0",
        }
        payload.update(changes)
        return self.client.post(self.url, payload)

    def test_normal_sync_is_internal_idempotent_and_auditable(self):
        self.client.force_login(self.technician)
        first = self.submit()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["code"], "saved")
        note = JobNote.objects.get(client_operation_id=self.key)
        self.assertEqual(note.author, self.technician)
        self.assertTrue(note.is_internal)
        self.assertEqual(note.job, self.job)
        repeated = self.submit()
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()["code"], "already_saved")
        self.assertEqual(JobNote.objects.filter(client_operation_id=self.key).count(), 1)

    def test_changed_job_is_not_silently_overwritten(self):
        self.client.force_login(self.technician)
        old_version = self.job.updated_at.isoformat()
        self.job.status = JobCard.STATUS_DIAGNOSING
        self.job.save()
        stale = self.submit(base_version=old_version)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "job_changed")
        self.assertFalse(JobNote.objects.filter(client_operation_id=self.key).exists())
        self.job.refresh_from_db()
        self.assertEqual(self.submit().status_code, 201)

    def test_closed_job_rejects_queued_notes(self):
        self.client.force_login(self.technician)
        self.job.status = JobCard.STATUS_CANCELLED
        self.job.save()
        self.job.refresh_from_db()
        result = self.submit()
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.json()["code"], "job_closed")
        self.assertFalse(JobNote.objects.filter(client_operation_id=self.key).exists())

    def test_duplicate_id_reuse_for_changed_content_or_other_user_is_blocked(self):
        self.client.force_login(self.technician)
        self.submit()
        replay = self.submit(body="Different observation")
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(replay.json()["code"], "key_conflict")
        self.technician = get_user_model().objects.create_user(
            username="field-tech-2", password="pw", is_staff=True
        )
        self.technician.user_permissions.add(
            Permission.objects.get(codename="add_jobnote")
        )
        self.client.force_login(self.technician)
        reused = self.submit()
        self.assertEqual(reused.status_code, 409)
        self.assertEqual(reused.json()["code"], "key_conflict")
        self.assertEqual(JobNote.objects.count(), 1)

    def test_customer_anonymous_and_unpermitted_staff_are_denied(self):
        self.assertEqual(self.submit().status_code, 401)
        self.client.force_login(self.customer_user)
        self.assertEqual(self.submit().status_code, 403)
        self.client.force_login(self.no_permission)
        self.assertEqual(self.submit().status_code, 403)
        self.assertEqual(JobNote.objects.count(), 0)

    def test_validation_rejects_invalid_ids_missing_versions_and_long_notes(self):
        self.client.force_login(self.technician)
        cases = [
            {"operation_id": "invalid"},
            {"operation_id": str(uuid4()).upper()},
            {"body": ""},
            {"body": "X" * 3001},
            {"base_version": ""},
        ]
        for values in cases:
            with self.subTest(values=list(values)):
                response = self.submit(**values)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(JobNote.objects.count(), 0)

    def test_field_ui_is_reachable_for_authorized_staff_only(self):
        self.client.force_login(self.technician)
        detail = self.client.get(reverse("staff_job_bench_detail", args=[self.job.pk]))
        self.assertContains(detail, "Save to this device")
        self.assertContains(detail, self.job.updated_at.isoformat())
        self.assertContains(detail, self.url)
        self.assertContains(detail, "field_notes_offline.js")
        self.client.force_login(self.no_permission)
        denied = self.client.get(reverse("staff_job_bench_detail", args=[self.job.pk]))
        self.assertNotContains(denied, "Save to this device")

    def test_csrf_protection_on_offline_sync(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.technician)
        blocked = client.post(self.url, {
            "operation_id": str(self.key), "base_version": self.job.updated_at.isoformat(),
            "body": "CSRF must be required",
        })
        self.assertEqual(blocked.status_code, 403)
        self.assertFalse(JobNote.objects.filter(client_operation_id=self.key).exists())

    def test_closed_job_shows_discard_ui_without_active_sync(self):
        self.job.status = JobCard.STATUS_CANCELLED
        self.job.save()
        self.client.force_login(self.technician)
        response = self.client.get(reverse("staff_job_detail", args=[self.job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-offline-open="no"')
        self.assertContains(response, "This job is closed.")
        self.assertContains(response, "Discard queued notes")

    def test_active_job_shows_private_queue_preview(self):
        self.client.force_login(self.technician)
        response = self.client.get(reverse("staff_job_detail", args=[self.job.pk]))
        self.assertContains(response, 'data-offline-open="yes"')
        self.assertContains(response, "Device-only unsynced notes")
        self.assertContains(response, "field_notes_offline.js")
