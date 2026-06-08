from django.conf import settings
from django.db import models
from django.utils import timezone


class OutboundEmail(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    to_email = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    error = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="outbound_emails_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    # Links
    commercial_document = models.ForeignKey(
        "billing.CommercialDocument",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outbound_emails",
    )
    job_card = models.ForeignKey(
        "operations.JobCard",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outbound_emails",
    )

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.to_email} — {self.subject}"

    def mark_sent(self) -> None:
        self.status = self.STATUS_SENT
        self.sent_at = timezone.now()

    def mark_failed(self, error: str) -> None:
        self.status = self.STATUS_FAILED
        self.error = error
        self.sent_at = timezone.now()
