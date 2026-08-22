from datetime import timedelta

from django import forms
from django.conf import settings
from django.utils import timezone

from customer_campaigns.models import CustomerCampaign


class BootstrapFormMixin:
    def _apply_bootstrap(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class CustomerCampaignForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CustomerCampaign
        fields = (
            "name",
            "marketing_campaign",
            "channel",
            "topic",
            "segment",
            "target_product",
            "minimum_customer_spend",
            "location_query",
            "subject",
            "body",
            "max_recipients",
        )
        widgets = {
            "body": forms.Textarea(attrs={"rows": 10}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["marketing_campaign"].required = False
        self.fields["marketing_campaign"].help_text = (
            "Optional link to the broader marketing campaign for reporting."
        )
        self.fields["channel"].help_text = (
            "Email can use bounded delivery. WhatsApp creates a consent-checked "
            "click-to-chat queue that staff send and confirm manually."
        )
        self.fields["target_product"].required = False
        self.fields["target_product"].help_text = "Required for product-interest campaigns; optional for other audiences."
        self.fields["minimum_customer_spend"].help_text = "Optional minimum lifetime order value in UGX."
        self.fields["location_query"].help_text = "Optional city, region, or address keyword."
        self.fields["max_recipients"].help_text = (
            "Preparation will stop at this number. The production maximum is "
            f"{getattr(settings, 'CUSTOMER_CAMPAIGN_MAX_RECIPIENTS', 100)}."
        )
        self._apply_bootstrap()

    def clean_max_recipients(self):
        value = self.cleaned_data["max_recipients"]
        configured_max = int(getattr(settings, "CUSTOMER_CAMPAIGN_MAX_RECIPIENTS", 100))
        if value > configured_max:
            raise forms.ValidationError(
                f"Use {configured_max} recipients or fewer for one campaign."
            )
        return value

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("segment") == CustomerCampaign.SEGMENT_PRODUCT_INTEREST and not cleaned_data.get("target_product"):
            self.add_error("target_product", "Choose the product customers asked about.")
        if (
            cleaned_data.get("channel") == CustomerCampaign.CHANNEL_WHATSAPP
            and len(cleaned_data.get("body") or "") > 1500
        ):
            self.add_error(
                "body",
                "Keep manual WhatsApp messages to 1,500 characters or fewer.",
            )
        return cleaned_data


class CampaignApprovalForm(BootstrapFormMixin, forms.Form):
    approval_note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Record what was reviewed before approval.",
    )
    confirm_approval = forms.BooleanField(
        label="I reviewed the audience, subject, body and unsubscribe control.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()


class CampaignSendForm(BootstrapFormMixin, forms.Form):
    confirmation = forms.CharField(
        help_text="Enter the exact confirmation phrase shown below.",
    )
    batch_size = forms.IntegerField(
        min_value=1,
        required=False,
        help_text=(
            "Leave blank to use the configured safe batch size. A larger value is "
            "automatically reduced to the configured maximum."
        ),
    )

    def __init__(self, *args, campaign: CustomerCampaign, **kwargs):
        self.campaign = campaign
        super().__init__(*args, **kwargs)
        self.expected_confirmation = f"SEND {campaign.pk}"
        self.fields["confirmation"].label = (
            f"Type {self.expected_confirmation} to send the next batch"
        )
        self._apply_bootstrap()

    def clean_confirmation(self):
        value = (self.cleaned_data["confirmation"] or "").strip()
        if value != self.expected_confirmation:
            raise forms.ValidationError("The confirmation phrase does not match.")
        return value


class CampaignScheduleForm(BootstrapFormMixin, forms.Form):
    scheduled_for = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
        input_formats=["%Y-%m-%dT%H:%M"],
        help_text="The existing automation timer checks due campaigns every 15 minutes.",
    )
    batch_size = forms.IntegerField(
        min_value=1,
        help_text="Maximum recipients released by each automated run.",
    )
    confirmation = forms.CharField()

    def __init__(self, *args, campaign: CustomerCampaign, **kwargs):
        self.campaign = campaign
        super().__init__(*args, **kwargs)
        configured_batch = int(
            getattr(settings, "CUSTOMER_CAMPAIGN_AUTOMATION_BATCH_SIZE", 1)
        )
        self.fields["batch_size"].max_value = configured_batch
        self.fields["batch_size"].initial = configured_batch
        self.fields["scheduled_for"].initial = timezone.localtime(
            timezone.now() + timedelta(minutes=15)
        ).strftime("%Y-%m-%dT%H:%M")
        self.expected_confirmation = f"SCHEDULE {campaign.pk}"
        self.fields["confirmation"].label = (
            f"Type {self.expected_confirmation} to activate scheduled delivery"
        )
        self._apply_bootstrap()

    def clean_confirmation(self):
        value = (self.cleaned_data["confirmation"] or "").strip()
        if value != self.expected_confirmation:
            raise forms.ValidationError("The schedule confirmation phrase does not match.")
        return value

    def clean_scheduled_for(self):
        value = self.cleaned_data["scheduled_for"]
        now = timezone.now()
        if value <= now:
            raise forms.ValidationError("Choose a future date and time.")
        lead_hours = int(
            getattr(settings, "CUSTOMER_CAMPAIGN_SCHEDULE_MAX_LEAD_HOURS", 24)
        )
        if value > now + timedelta(hours=lead_hours):
            raise forms.ValidationError(
                f"Schedule this campaign within the next {lead_hours} hours."
            )
        if self.campaign.approval_expires_at and value >= self.campaign.approval_expires_at:
            raise forms.ValidationError("The schedule must be before approval expiry.")
        return value


class CampaignPauseForm(BootstrapFormMixin, forms.Form):
    reason = forms.CharField(
        max_length=240,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Explain why automated delivery is being paused.",
    )
    confirmation = forms.CharField()

    def __init__(self, *args, campaign: CustomerCampaign, **kwargs):
        self.campaign = campaign
        super().__init__(*args, **kwargs)
        self.expected_confirmation = f"PAUSE {campaign.pk}"
        self.fields["confirmation"].label = f"Type {self.expected_confirmation} to pause"
        self._apply_bootstrap()

    def clean_confirmation(self):
        value = (self.cleaned_data["confirmation"] or "").strip()
        if value != self.expected_confirmation:
            raise forms.ValidationError("The pause confirmation phrase does not match.")
        return value


class CampaignResumeForm(BootstrapFormMixin, forms.Form):
    next_run_at = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
        input_formats=["%Y-%m-%dT%H:%M"],
        help_text="Choose when the next bounded automated batch may run.",
    )
    confirmation = forms.CharField()

    def __init__(self, *args, campaign: CustomerCampaign, **kwargs):
        self.campaign = campaign
        super().__init__(*args, **kwargs)
        self.fields["next_run_at"].initial = timezone.localtime(
            timezone.now() + timedelta(minutes=15)
        ).strftime("%Y-%m-%dT%H:%M")
        self.expected_confirmation = f"RESUME {campaign.pk}"
        self.fields["confirmation"].label = f"Type {self.expected_confirmation} to resume"
        self._apply_bootstrap()

    def clean_confirmation(self):
        value = (self.cleaned_data["confirmation"] or "").strip()
        if value != self.expected_confirmation:
            raise forms.ValidationError("The resume confirmation phrase does not match.")
        return value

    def clean_next_run_at(self):
        value = self.cleaned_data["next_run_at"]
        if self.campaign.approval_expires_at and value >= self.campaign.approval_expires_at:
            raise forms.ValidationError("The resume time must be before approval expiry.")
        return value
