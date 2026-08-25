from django.conf import settings
from django.db import models


class CustomerFollowUp(models.Model):
    TYPE_WARRANTY_EXPIRY = "warranty_expiry"
    TYPE_DORMANT_CUSTOMER = "dormant_customer"
    TYPE_CHOICES = [
        (TYPE_WARRANTY_EXPIRY, "Warranty expiry check-in"),
        (TYPE_DORMANT_CUSTOMER, "Dormant customer follow-up"),
    ]

    STATUS_PENDING = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_DISMISSED = "dismissed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_IN_PROGRESS, "In progress"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_DISMISSED, "Dismissed"),
    ]

    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"
    PRIORITY_CHOICES = [
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_URGENT, "Urgent"),
    ]

    idempotency_key = models.CharField(max_length=180, unique=True, db_index=True)
    follow_up_type = models.CharField(max_length=24, choices=TYPE_CHOICES, db_index=True)
    customer = models.ForeignKey(
        "crm.Customer", on_delete=models.CASCADE, related_name="retention_followups"
    )
    product_serial = models.ForeignKey(
        "catalog.ProductSerial", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="retention_followups",
    )
    order = models.ForeignKey(
        "commerce.Order", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="retention_followups",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_customer_followups",
    )
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    priority = models.CharField(
        max_length=12, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL
    )
    due_at = models.DateTimeField(db_index=True)
    note = models.CharField(max_length=500, blank=True)
    last_contacted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="completed_customer_followups",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "due_at"], name="retention_followup_due_idx")
        ]

    def __str__(self):
        return f"{self.customer.name}: {self.get_follow_up_type_display()}"

    @property
    def is_open(self):
        return self.status in {self.STATUS_PENDING, self.STATUS_IN_PROGRESS}
