import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from billing.models import CommercialDocument, allocate_document_number
from commerce.models import Order
from crm.models import Customer


class JobCard(models.Model):
    STATUS_INTAKE = "intake"
    STATUS_DIAGNOSING = "diagnosing"
    STATUS_AWAITING_PARTS = "awaiting_parts"
    STATUS_IN_REPAIR = "in_repair"
    STATUS_QA = "qa"
    STATUS_READY = "ready_pickup"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_INTAKE, "Intake"),
        (STATUS_DIAGNOSING, "Diagnosing"),
        (STATUS_AWAITING_PARTS, "Awaiting parts"),
        (STATUS_IN_REPAIR, "In repair"),
        (STATUS_QA, "QA / testing"),
        (STATUS_READY, "Ready for pickup"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_URGENT, "Urgent"),
    ]

    number = models.CharField(
        max_length=32, unique=True, db_index=True, blank=True, default=""
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="job_cards"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    device_type = models.CharField(max_length=120, blank=True)
    device_make = models.CharField(max_length=120, blank=True)
    device_model = models.CharField(max_length=120, blank=True)
    serial_number = models.CharField(max_length=120, blank=True)
    customer_signature = models.ImageField(
        upload_to="job_signatures/%Y/%m/",
        blank=True,
        null=True,
        help_text="Optional customer sign-off image.",
    )
    accessories_received = models.TextField(blank=True)
    problem_reported = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True)
    resolution = models.TextField(blank=True)
    status = models.CharField(
        max_length=32, choices=STATUS_CHOICES, default=STATUS_INTAKE
    )
    priority = models.CharField(
        max_length=16, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_jobs",
    )
    labor_hours = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0"), blank=True
    )
    received_on = models.DateTimeField(default=timezone.now)
    scheduled_for = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional customer appointment or bench slot.",
    )
    scheduled_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="End of appointment window (defaults to 1 hour after start).",
    )
    estimated_completion = models.DateField(null=True, blank=True)
    status_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Automatically set when status last changed.",
    )
    closed_on = models.DateTimeField(null=True, blank=True)
    related_order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_cards",
    )
    related_invoice = models.ForeignKey(
        CommercialDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_cards",
        limit_choices_to={"doc_type": CommercialDocument.TYPE_INVOICE},
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-received_on"]

    def __str__(self) -> str:
        return f"{self.number} — {self.title}"

    @property
    def days_in_current_status(self) -> int:
        """Whole days since last status change (or since received if unknown)."""
        anchor = self.status_changed_at or self.received_on
        if anchor is None:
            return 0
        delta = timezone.now() - anchor
        return max(0, delta.days)

    @property
    def is_open(self) -> bool:
        return self.status not in (self.STATUS_COMPLETED, self.STATUS_CANCELLED)

    @property
    def sla_due_at(self):
        from core.models import CompanySettings

        if not self.received_on:
            return None
        hours = CompanySettings.load().sla_hours_for(self.priority)
        return self.received_on + timedelta(hours=hours)

    @property
    def is_overdue(self) -> bool:
        due = self.sla_due_at
        if due is None or not self.is_open:
            return False
        return timezone.now() > due

    @property
    def due_in_label(self) -> str:
        from core.models import _due_in_label

        return _due_in_label(self.sla_due_at, self.is_open)

    def clean(self) -> None:
        super().clean()
        if not self.pk:
            if self.status != self.STATUS_INTAKE:
                raise ValidationError(
                    {"status": "New job cards must start in Intake."}
                )
        else:
            prev = (
                JobCard.objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            from operations.job_status import validate_job_status_transition

            validate_job_status_transition(previous=prev, new=self.status)
        if self.customer_id:
            if self.related_invoice_id:
                if (
                    self.related_invoice.customer_id is not None
                    and self.related_invoice.customer_id != self.customer_id
                ):
                    raise ValidationError({
                        "related_invoice": "Invoice belongs to a different customer."
                    })
                if (
                    self.related_invoice.doc_type !=
                    self.related_invoice.TYPE_INVOICE
                ):
                    raise ValidationError({
                        "related_invoice": "Only a customer invoice can be linked."
                    })
            if self.related_order_id and (
                self.related_order.customer_id is not None
                and self.related_order.customer_id != self.customer_id
            ):
                raise ValidationError({
                    "related_order": "Order belongs to a different customer."
                })
        self._validate_schedule_overlap()

    def _schedule_window(self) -> tuple:
        if not self.scheduled_for:
            return None, None
        end = self.scheduled_until
        if end is None:
            end = self.scheduled_for + timedelta(hours=1)
        return self.scheduled_for, end

    def _validate_schedule_overlap(self) -> None:
        start, end = self._schedule_window()
        if not start or not end or not self.assigned_to_id:
            return
        if end <= start:
            raise ValidationError(
                {"scheduled_until": "Appointment end must be after the start time."}
            )
        qs = JobCard.objects.filter(
            assigned_to_id=self.assigned_to_id,
            scheduled_for__isnull=False,
        ).exclude(status=self.STATUS_CANCELLED)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        for other in qs.only("pk", "number", "scheduled_for", "scheduled_until"):
            o_start = other.scheduled_for
            o_end = other.scheduled_until or (o_start + timedelta(hours=1))
            if o_start < end and o_end > start:
                raise ValidationError(
                    {
                        "scheduled_for": (
                            f"Overlaps with job {other.number} "
                            f"({o_start:%Y-%m-%d %H:%M}–{o_end:%H:%M})."
                        )
                    }
                )

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.scheduled_for and not self.scheduled_until:
            self.scheduled_until = self.scheduled_for + timedelta(hours=1)
        if not self.number:
            self.number = allocate_document_number("JC")
        old_status = None
        if self.pk:
            old_status = (
                JobCard.objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
        if old_status is not None and old_status != self.status:
            self.status_changed_at = timezone.now()
            if self.status in (self.STATUS_COMPLETED, self.STATUS_CANCELLED):
                if self.closed_on is None:
                    self.closed_on = timezone.now()
            elif old_status in (self.STATUS_COMPLETED, self.STATUS_CANCELLED):
                self.closed_on = None
        old_assignee = None
        if self.pk:
            old_assignee = (
                JobCard.objects.filter(pk=self.pk)
                .values_list("assigned_to_id", flat=True)
                .first()
            )
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new or (old_status is not None and old_status != self.status):
            JobStatusEvent.objects.create(
                job=self,
                from_status=old_status or "",
                to_status=self.status,
                actor=getattr(self, "_status_actor", None),
                note=getattr(self, "_status_note", "")[:300],
            )
            if (
                old_status is not None
                and self.status == self.STATUS_CANCELLED
                and old_status != self.STATUS_CANCELLED
            ):
                self._auto_return_parts_to_stock()
        if self.assigned_to_id and self.assigned_to_id != old_assignee:
            from django.urls import reverse

            from core.notifications import staff_notify

            staff_notify(
                self.assigned_to,
                f"Job {self.number} assigned to you",
                reverse("staff_job_detail", kwargs={"pk": self.pk}),
            )

    def _auto_return_parts_to_stock(self) -> None:
        """When a job is cancelled, reverse every consumed-part adjustment."""
        from inventory.models import StockAdjustment

        consumed = StockAdjustment.objects.filter(
            job=self,
            reason=StockAdjustment.REASON_JOB,
            quantity_delta__lt=0,
        )
        for original in consumed:
            reversal = StockAdjustment(
                product=original.product,
                product_variant=original.product_variant,
                quantity_delta=-int(original.quantity_delta),
                reason=StockAdjustment.REASON_RETURN,
                note=f"Auto-return on cancel of {self.number}",
                job=self,
                created_by=getattr(self, "_status_actor", None),
            )
            reversal.save()
            reversal.apply()


class JobExpense(models.Model):
    """Recorded direct cost on a repair or installation; not an invoice/payment.

    Every entry needs a source reference so duplicate submissions cannot
    silently increase reported costs. Existing parts movements and time
    entries remain separate; no invented unit costs are implied here.
    """

    CATEGORY_PARTS = "parts"
    CATEGORY_LABOUR = "labour"
    CATEGORY_TRANSPORT = "transport"
    CATEGORY_SUBCONTRACTOR = "subcontractor"
    CATEGORY_OTHER = "other"
    CATEGORY_CHOICES = [
        (CATEGORY_PARTS, "Direct parts purchase"),
        (CATEGORY_LABOUR, "Actual labour cost"),
        (CATEGORY_TRANSPORT, "Transport and field travel"),
        (CATEGORY_SUBCONTRACTOR, "Subcontractor / external service"),
        (CATEGORY_OTHER, "Other direct expense"),
    ]

    job = models.ForeignKey(
        JobCard, on_delete=models.PROTECT, related_name="expenses"
    )
    category = models.CharField(max_length=24, choices=CATEGORY_CHOICES)
    description = models.CharField(max_length=255)
    reference = models.CharField(
        max_length=120,
        help_text="Unique receipt, payment, job voucher or supplier invoice reference.",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="job_expenses_recorded",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "reference"],
                name="unique_expense_reference_per_job",
            ),
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name="job_expense_amount_positive",
            ),
        ]

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Record a positive actual cost."})
        self.reference = (self.reference or "").strip()
        if not self.reference:
            raise ValidationError(
                {"reference": "A source receipt or voucher reference is required."}
            )

    def __str__(self):
        return f"{self.job.number}: {self.reference} ({self.amount})"


class JobNote(models.Model):
    job = models.ForeignKey(JobCard, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    body = models.TextField()
    is_internal = models.BooleanField(
        default=True, help_text="Hidden from customer-facing exports."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class TimeEntry(models.Model):
    job = models.ForeignKey(JobCard, on_delete=models.CASCADE, related_name="time_entries")
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="time_entries",
    )
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    minutes = models.PositiveIntegerField(default=0, help_text="Stored as minutes for reporting.")
    is_billable = models.BooleanField(default=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at", "-id"]

    def __str__(self) -> str:
        return f"{self.job.number} — {self.technician} ({self.minutes}m)"


class JobStatusEvent(models.Model):
    """Append-only timeline of status changes on a JobCard."""

    job = models.ForeignKey(
        JobCard, on_delete=models.CASCADE, related_name="status_events"
    )
    from_status = models.CharField(max_length=32, blank=True)
    to_status = models.CharField(max_length=32)
    note = models.CharField(max_length=300, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_status_events",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.job.number}: {self.from_status or '∅'} → {self.to_status}"


class JobHandover(models.Model):
    """One-time staff-confirmed collection or delivery; not a payment receipt."""

    METHOD_COLLECTION = "collection"
    METHOD_DELIVERY = "delivery"
    METHOD_CHOICES = [
        (METHOD_COLLECTION, "Collected at LEOSOFT"),
        (METHOD_DELIVERY, "Delivered to recipient"),
    ]

    job = models.OneToOneField(
        JobCard, on_delete=models.PROTECT, related_name="handover"
    )
    recipient_name = models.CharField(max_length=160)
    method = models.CharField(max_length=16, choices=METHOD_CHOICES)
    note = models.CharField(max_length=300, blank=True)
    signature = models.ImageField(
        upload_to="job_signatures/handover/%Y/%m/",
        blank=True,
        help_text="Protected recipient signature captured at completed-work handover.",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="job_handovers_recorded",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "-id"]

    def __str__(self):
        return f"{self.job.number}: {self.get_method_display()}"


class JobFeedback(models.Model):
    """Customer satisfaction rating after job completion."""

    RATING_CHOICES = [(i, f"{i} star{'s' if i != 1 else ''}") for i in range(1, 6)]

    job = models.OneToOneField(
        JobCard, on_delete=models.CASCADE, related_name="feedback"
    )
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    comment = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    response_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self) -> str:
        return f"{self.job.number}: {self.rating}★"


class JobAttachment(models.Model):
    """Work-in-progress photos linked to a job card."""

    job = models.ForeignKey(
        JobCard,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    image = models.ImageField(upload_to="job_attachments/%Y/%m/")
    caption = models.CharField(max_length=200, blank=True)
    show_to_customer = models.BooleanField(
        default=True,
        help_text="If enabled, the image appears in the customer portal for this job.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.job.number} attachment"
