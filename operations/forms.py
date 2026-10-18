from django import forms

from operations.models import JobAttachment, JobCard, JobExpense, JobHandover, JobNote, TimeEntry


class JobCardForm(forms.ModelForm):
    class Meta:
        model = JobCard
        fields = (
            "customer",
            "title",
            "description",
            "device_type",
            "device_make",
            "device_model",
            "serial_number",
            "accessories_received",
            "problem_reported",
            "diagnosis",
            "resolution",
            "status",
            "priority",
            "assigned_to",
            "labor_hours",
            "estimated_completion",
            "scheduled_for",
            "scheduled_until",
            "related_order",
            "related_invoice",
            "customer_signature",
        )
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "device_type": forms.TextInput(attrs={"class": "form-control"}),
            "device_make": forms.TextInput(attrs={"class": "form-control"}),
            "device_model": forms.TextInput(attrs={"class": "form-control"}),
            "serial_number": forms.TextInput(attrs={"class": "form-control"}),
            "accessories_received": forms.Textarea(
                attrs={"class": "form-control", "rows": 2}
            ),
            "problem_reported": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
            "diagnosis": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "resolution": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "assigned_to": forms.Select(attrs={"class": "form-select"}),
            "labor_hours": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.25"}
            ),
            "estimated_completion": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "scheduled_for": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"}
            ),
            "scheduled_until": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"}
            ),
            "related_order": forms.Select(attrs={"class": "form-select"}),
            "related_invoice": forms.Select(attrs={"class": "form-select"}),
            "customer_signature": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def save(self, commit=True):
        prev_status = None
        if self.instance.pk:
            prev_status = (
                JobCard.objects.filter(pk=self.instance.pk)
                .values_list("status", flat=True)
                .first()
            )
        obj = super().save(commit=commit)
        if (
            commit
            and prev_status is not None
            and prev_status != obj.status
        ):
            user = getattr(self, "_audit_user", None)
            from core.audit import log_audit_event

            log_audit_event(
                actor=user,
                verb="job.status_change",
                summary=f"{obj.number}: {prev_status} → {obj.status}",
                target=obj,
            )
        return obj


class JobHandoverForm(forms.ModelForm):
    confirmed = forms.BooleanField(
        required=True,
        label="I confirm the device or completed work was handed over",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = JobHandover
        fields = ("recipient_name", "method", "note")
        widgets = {
            "recipient_name": forms.TextInput(attrs={
                "class": "form-control", "maxlength": "160",
                "placeholder": "Person receiving the device or service",
            }),
            "method": forms.Select(attrs={"class": "form-select"}),
            "note": forms.TextInput(attrs={
                "class": "form-control", "maxlength": "300",
                "placeholder": "Optional collection or delivery reference",
            }),
        }


class JobExpenseForm(forms.ModelForm):
    class Meta:
        model = JobExpense
        fields = ("category", "description", "reference", "amount")
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "description": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "What was paid for?"
            }),
            "reference": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Receipt or voucher ID"
            }),
            "amount": forms.NumberInput(attrs={
                "class": "form-control", "min": "0.01", "step": "0.01"
            }),
        }


class JobNoteForm(forms.ModelForm):
    class Meta:
        model = JobNote
        fields = ("body", "is_internal")
        widgets = {
            "body": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_internal": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_internal"].label = "Internal note (hidden from customer portal)"


class JobAttachmentForm(forms.ModelForm):
    class Meta:
        model = JobAttachment
        fields = ("image", "caption", "show_to_customer")
        widgets = {
            "image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "caption": forms.TextInput(attrs={"class": "form-control"}),
            "show_to_customer": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["show_to_customer"].label = "Show in customer portal"


class TimeEntryForm(forms.ModelForm):
    class Meta:
        model = TimeEntry
        fields = ("technician", "started_at", "ended_at", "minutes", "is_billable", "note")
        widgets = {
            "technician": forms.Select(attrs={"class": "form-select"}),
            "started_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "ended_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "minutes": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "is_billable": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "note": forms.TextInput(attrs={"class": "form-control"}),
        }
