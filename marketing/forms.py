from django import forms
from django.contrib.auth import get_user_model

from automation.models import PostAutomationPlan
from automation.services import configure_post_plan
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
        help_text=(
            "Facebook and Instagram publish through Meta, and Telegram through its "
            "free Bot API, after credentials are connected. Other channels remain manual."
        ),
    )
    publish_mode = forms.ChoiceField(
        choices=PostAutomationPlan.MODE_CHOICES,
        initial=PostAutomationPlan.MODE_MANUAL,
        help_text=(
            "Automatic mode is an approval to publish through configured official "
            "connectors when the scheduled time arrives."
        ),
    )
    media_url = forms.URLField(
        required=False,
        help_text=(
            "Optional public HTTPS image URL. When blank, the selected product's "
            "public image is used. Instagram requires an image."
        ),
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
            "publish_mode",
            "media_url",
            "status",
            "scheduled_for",
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
            try:
                plan = self.instance.automation_plan
            except PostAutomationPlan.DoesNotExist:
                plan = None
            if plan:
                self.initial["publish_mode"] = plan.mode
                self.initial["media_url"] = plan.media_url

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        scheduled_for = cleaned.get("scheduled_for")
        product = cleaned.get("product")
        template = cleaned.get("caption_template")
        caption = (cleaned.get("caption") or "").strip()
        channels = set(cleaned.get("channels") or [])
        publish_mode = cleaned.get("publish_mode")
        media_url = (cleaned.get("media_url") or "").strip()

        if status == ScheduledPost.STATUS_SCHEDULED and not scheduled_for:
            self.add_error("scheduled_for", "Choose a publishing date and time.")
        if not caption and template:
            caption = render_caption(template, product=product)
            cleaned["caption"] = caption
        if not caption:
            self.add_error("caption", "Enter a caption or select a caption template.")

        has_product_image = bool(product and product.primary_display_image)
        if (
            publish_mode == PostAutomationPlan.MODE_AUTOMATIC
            and "instagram" in channels
            and not media_url
            and not has_product_image
        ):
            self.add_error(
                "media_url",
                "Instagram automatic publishing requires a public image URL or a product image.",
            )
        if media_url and not media_url.lower().startswith("https://"):
            self.add_error("media_url", "Use a public HTTPS image URL.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.channels = self.cleaned_data.get("channels", [])
        instance.caption = self.cleaned_data.get("caption", "")
        if commit:
            instance.save()
            configure_post_plan(
                instance,
                mode=self.cleaned_data.get("publish_mode"),
                media_url=self.cleaned_data.get("media_url") or "",
            )
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
            "request_type",
            "priority",
            "status",
            "loss_reason",
            "estimated_value",
            "assigned_to",
            "next_follow_up_at",
            "notes",
        )
        widgets = {
            "next_follow_up_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["next_follow_up_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["next_follow_up_at"].help_text = (
            "Set the next promised contact time. Won and lost leads clear this automatically."
        )
        self.fields["assigned_to"].queryset = get_user_model().objects.filter(
            is_staff=True,
            is_active=True,
        ).order_by("username")
        self.fields["request_type"].required = False
        self.fields["priority"].required = False
        self.fields["loss_reason"].help_text = (
            "Record why a sale was lost so recurring commercial problems can be fixed."
        )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("status") == MarketingLead.STATUS_LOST and not cleaned_data.get("loss_reason"):
            self.add_error("loss_reason", "Choose the main reason this sale was lost.")
        if cleaned_data.get("status") != MarketingLead.STATUS_LOST:
            cleaned_data["loss_reason"] = ""
        return cleaned_data

    def clean_request_type(self):
        return self.cleaned_data.get("request_type") or self.instance.request_type or "other"

    def clean_priority(self):
        return (
            self.cleaned_data.get("priority")
            or self.instance.priority
            or MarketingLead.PRIORITY_NORMAL
        )
