from django import forms

from messaging.deliverability import normalize_email
from messaging.models import EmailSuppression


class SendEmailForm(forms.Form):
    to_email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))
    subject = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    body = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )
    attach_pdf = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class ManualEmailSuppressionForm(forms.Form):
    email_address = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-control"})
    )
    scope = forms.ChoiceField(
        choices=EmailSuppression.SCOPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason = forms.ChoiceField(
        choices=[
            (EmailSuppression.REASON_MANUAL, "Manual block"),
            (EmailSuppression.REASON_INVALID, "Invalid address"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    note = forms.CharField(
        min_length=8,
        max_length=300,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    confirmation = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control"}),
        help_text="Type SUPPRESS followed by the email address.",
    )

    def clean_email_address(self):
        return normalize_email(self.cleaned_data["email_address"])

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email_address")
        confirmation = (cleaned.get("confirmation") or "").strip()
        if email and confirmation != f"SUPPRESS {email}":
            self.add_error(
                "confirmation",
                f"Type SUPPRESS {email} exactly.",
            )
        return cleaned


class ReleaseEmailSuppressionForm(forms.Form):
    release_reason = forms.CharField(
        min_length=8,
        max_length=300,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    confirmation = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, suppression: EmailSuppression, **kwargs):
        self.suppression = suppression
        super().__init__(*args, **kwargs)
        self.fields["confirmation"].label = (
            f"Type RELEASE {suppression.email_address}"
        )

    def clean_confirmation(self):
        value = (self.cleaned_data.get("confirmation") or "").strip()
        expected = f"RELEASE {self.suppression.email_address}"
        if value != expected:
            raise forms.ValidationError(f"Type {expected} exactly.")
        return value


class RetryOutboundEmailForm(forms.Form):
    confirmation = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control"})
    )

    def __init__(self, *args, outbound_email, **kwargs):
        self.outbound_email = outbound_email
        super().__init__(*args, **kwargs)
        self.fields["confirmation"].label = (
            f"Type RETRY {outbound_email.pk}"
        )

    def clean_confirmation(self):
        value = (self.cleaned_data.get("confirmation") or "").strip()
        expected = f"RETRY {self.outbound_email.pk}"
        if value != expected:
            raise forms.ValidationError(f"Type {expected} exactly.")
        return value
