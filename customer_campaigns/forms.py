from django import forms
from django.conf import settings

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
            "topic",
            "segment",
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
