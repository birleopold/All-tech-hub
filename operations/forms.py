import base64
import binascii
from io import BytesIO
from uuid import uuid4

from django import forms
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError


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


MAX_HANDOVER_SIGNATURE_BYTES = 512 * 1024


class JobHandoverForm(forms.ModelForm):
    confirmed = forms.BooleanField(
        required=True,
        label="I confirm the device or completed work was handed over",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    recipient_consent = forms.BooleanField(
        required=True,
        label="The recipient agrees to this signature being saved as handover evidence",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    signature_upload = forms.ImageField(
        required=False,
        label="Upload recipient signature image instead",
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": "image/png,image/jpeg",
        }),
    )
    signature_data = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
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

    @staticmethod
    def _normalise_signature(raw: bytes) -> ContentFile:
        if len(raw) > MAX_HANDOVER_SIGNATURE_BYTES:
            raise forms.ValidationError("Signature is too large. Use an image under 512 KB.")
        if not raw:
            raise forms.ValidationError("The signature image is empty.")
        try:
            with Image.open(BytesIO(raw), formats=("PNG", "JPEG")) as source:
                source.load()
                if not 100 <= source.width <= 2500 or not 40 <= source.height <= 1500:
                    raise forms.ValidationError(
                        "Signature dimensions must be between 100×40 and 2500×1500 pixels."
                    )
                # Strip metadata and rewrite the image to a plain PNG, so
                # uploaded content cannot retain appended HTML or EXIF data.
                foreground = source.convert("RGBA")
                canvas = Image.new("RGBA", foreground.size, (255, 255, 255, 255))
                canvas.alpha_composite(foreground)
                output = BytesIO()
                canvas.convert("RGB").save(output, format="PNG", optimize=True)
                encoded = output.getvalue()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise forms.ValidationError("Upload a valid PNG or JPEG signature image.") from exc
        if len(encoded) > MAX_HANDOVER_SIGNATURE_BYTES:
            raise forms.ValidationError("Signature is too large after processing.")
        return ContentFile(encoded, name=f"handover-{uuid4().hex}.png")

    def clean(self):
        values = super().clean()
        upload = values.get("signature_upload")
        data = (values.get("signature_data") or "").strip()
        if upload and data:
            raise forms.ValidationError("Use either the signature pad or an uploaded image.")
        if not upload and not data:
            raise forms.ValidationError(
                "Ask the recipient to sign in the signature pad, or upload their signature image."
            )
        if upload:
            if upload.size > MAX_HANDOVER_SIGNATURE_BYTES:
                raise forms.ValidationError("Signature is too large. Use an image under 512 KB.")
            values["validated_signature"] = self._normalise_signature(
                upload.read(MAX_HANDOVER_SIGNATURE_BYTES + 1)
            )
        else:
            prefix = "data:image/png;base64,"
            if not data.startswith(prefix):
                raise forms.ValidationError("Draw a signature or upload a PNG/JPEG image.")
            try:
                decoded = base64.b64decode(data[len(prefix):], validate=True)
            except (ValueError, binascii.Error) as exc:
                raise forms.ValidationError("The drawn signature could not be read.") from exc
            values["validated_signature"] = self._normalise_signature(decoded)
        return values


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
