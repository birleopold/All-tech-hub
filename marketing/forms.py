from django import forms

from marketing.models import (
    CampaignLink,
    CaptionTemplate,
    MarketingCampaign,
    MarketingLead,
    ScheduledPost,
)
from marketing.services import product_public_url, render_caption


CHANNEL_CHOICES = [
    ("whatsapp", "WhatsApp"),
    ("facebook", "Facebook"),
    ("instagram", "Instagram"),
    ("tiktok", "TikTok"),
    ("x", "X"),
    ("linkedin", "LinkedIn"),
    ("youtube", "YouTube"),
    ("telegram", "Telegram"),
    ("pinterest", "Pinterest"),
    ("email", "Email"),
]


class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                continue
            css = "form-select" if isinstance(widget, forms.Select) else "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()


class MarketingCampaignForm(BootstrapModelForm):
    class Meta:
        model = MarketingCampaign
        fields = (
            "name",
            "objective",
            "status",
            "start_date",
            "end_date",
            "budget",
            "target_audience",
            "notes",
        )
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "target_audience": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date cannot be before the start date.")
        return cleaned


class CaptionTemplateForm(BootstrapModelForm):
    class Meta:
        model = CaptionTemplate
        fields = ("name", "channel", "body", "hashtags", "is_active")
        widgets = {"body": forms.Textarea(attrs={"rows": 7})}


class CampaignLinkForm(BootstrapModelForm):
    class Meta:
        model = CampaignLink
        fields = (
            "name",
            "campaign",
            "product",
            "destination_url",
            "source",
            "medium",
            "content",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["destination_url"].required = False
        self.fields["destination_url"].help_text = (
            "Leave blank when a product or service is selected; its public URL will be used."
        )

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get("product")
        destination = cleaned.get("destination_url")
        if not destination and product:
            cleaned["destination_url"] = product_public_url(product)
        elif not destination:
            self.add_error(
                "destination_url", "Enter a destination URL or select a product/service."
            )
        if not cleaned.get("content") and product:
            cleaned["content"] = product.slug
        return cleaned


class ScheduledPostForm(BootstrapModelForm):
    channels = forms.MultipleChoiceField(
        choices=CHANNEL_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select every platform where this content should be published.",
    )
    caption_template = forms.ModelChoiceField(
        queryset=CaptionTemplate.objects.filter(is_active=True),
        required=False,
        help_text="Optional. Used to generate the caption when the caption box is empty.",
    )

    class Meta:
        model = ScheduledPost
        fields = (
            "title",
            "campaign",
            "product",
            "caption_template",
            "caption",
            "channels",
            "status",
            "scheduled_for",
            "external_url",
            "notes",
        )
        widgets = {
            "caption": forms.Textarea(attrs={"rows": 8}),
            "scheduled_for": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["caption"].required = False
        if self.instance and self.instance.pk:
            self.initial["channels"] = self.instance.channels

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        scheduled_for = cleaned.get("scheduled_for")
        product = cleaned.get("product")
        template = cleaned.get("caption_template")
        caption = (cleaned.get("caption") or "").strip()

        if status == ScheduledPost.STATUS_SCHEDULED and not scheduled_for:
            self.add_error("scheduled_for", "Choose a publishing date and time.")
        if not caption and template:
            caption = render_caption(template, product=product)
            cleaned["caption"] = caption
        if not caption:
            self.add_error("caption", "Enter a caption or select a caption template.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.channels = self.cleaned_data.get("channels", [])
        instance.caption = self.cleaned_data.get("caption", "")
        if commit:
            instance.save()
        return instance


class MarketingLeadForm(BootstrapModelForm):
    class Meta:
        model = MarketingLead
        fields = (
            "name",
            "email",
            "phone",
            "campaign",
            "link",
            "product",
            "source",
            "medium",
            "status",
            "estimated_value",
            "assigned_to",
            "notes",
        )
        widgets = {"notes": forms.Textarea(attrs={"rows": 5})}
