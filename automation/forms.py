from django import forms

from automation.models import AutomationJob, SocialAutopilotSettings


class BootstrapFormMixin:
    def apply_bootstrap(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class AutomationPauseForm(BootstrapFormMixin, forms.Form):
    SCOPE_ALL = "all"
    scope = forms.ChoiceField(
        choices=[(SCOPE_ALL, "All automation"), *AutomationJob.TYPE_CHOICES]
    )
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), max_length=300)
    confirmation = forms.CharField(
        help_text="Type PAUSE AUTOMATION exactly.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def clean_confirmation(self):
        value = (self.cleaned_data.get("confirmation") or "").strip()
        if value != "PAUSE AUTOMATION":
            raise forms.ValidationError("The pause confirmation phrase does not match.")
        return value


class AutomationResumeForm(BootstrapFormMixin, forms.Form):
    SCOPE_ALL = "all"
    scope = forms.ChoiceField(
        choices=[(SCOPE_ALL, "All automation"), *AutomationJob.TYPE_CHOICES]
    )
    confirmation = forms.CharField(
        help_text="Type RESUME AUTOMATION exactly.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def clean_confirmation(self):
        value = (self.cleaned_data.get("confirmation") or "").strip()
        if value != "RESUME AUTOMATION":
            raise forms.ValidationError("The resume confirmation phrase does not match.")
        return value


class AutomationJobReplayForm(BootstrapFormMixin, forms.Form):
    confirmation = forms.CharField()

    def __init__(self, *args, job: AutomationJob, **kwargs):
        self.job = job
        super().__init__(*args, **kwargs)
        self.expected_confirmation = f"REPLAY {job.pk}"
        self.fields["confirmation"].label = f"Type {self.expected_confirmation}"
        self.apply_bootstrap()

    def clean_confirmation(self):
        value = (self.cleaned_data.get("confirmation") or "").strip()
        if value != self.expected_confirmation:
            raise forms.ValidationError("The replay confirmation phrase does not match.")
        return value


class AutomationJobCancelForm(BootstrapFormMixin, forms.Form):
    reason = forms.CharField(
        required=False,
        max_length=300,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    confirmation = forms.CharField()

    def __init__(self, *args, job: AutomationJob, **kwargs):
        self.job = job
        super().__init__(*args, **kwargs)
        self.expected_confirmation = f"CANCEL {job.pk}"
        self.fields["confirmation"].label = f"Type {self.expected_confirmation}"
        self.apply_bootstrap()

    def clean_confirmation(self):
        value = (self.cleaned_data.get("confirmation") or "").strip()
        if value != self.expected_confirmation:
            raise forms.ValidationError("The cancellation phrase does not match.")
        return value


class SocialAutopilotForm(BootstrapFormMixin, forms.ModelForm):
    CHANNEL_CHOICES = [
        ("facebook", "Facebook Page"),
        ("instagram", "Instagram"),
        ("telegram", "Telegram channel"),
    ]
    channels = forms.MultipleChoiceField(
        choices=CHANNEL_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        help_text="Only connected channels publish automatically.",
    )
    posting_hours_text = forms.CharField(
        label="Posting hours",
        help_text="Kampala-local hours separated by commas, for example 9,18.",
    )

    class Meta:
        model = SocialAutopilotSettings
        fields = (
            "enabled",
            "mode",
            "channels",
            "posts_per_day",
            "posting_hours_text",
            "queue_days",
            "product_cooldown_days",
            "include_prices",
            "require_in_stock",
            "default_hashtags",
            "preferred_product",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["channels"] = self.instance.channels or [
            "facebook",
            "instagram",
            "telegram",
        ]
        self.initial["posting_hours_text"] = ",".join(
            str(value) for value in (self.instance.posting_hours or [9, 18])
        )
        self.fields["preferred_product"].queryset = (
            self.fields["preferred_product"].queryset.filter(
                is_published=True
            ).order_by("-is_featured", "name")
        )
        self.apply_bootstrap()

    def clean_posts_per_day(self):
        value = int(self.cleaned_data["posts_per_day"])
        if not 1 <= value <= 4:
            raise forms.ValidationError("Choose between 1 and 4 daily posting slots.")
        return value

    def clean_queue_days(self):
        value = int(self.cleaned_data["queue_days"])
        if not 1 <= value <= 14:
            raise forms.ValidationError("Queue between 1 and 14 days.")
        return value

    def clean_product_cooldown_days(self):
        value = int(self.cleaned_data["product_cooldown_days"])
        if not 1 <= value <= 90:
            raise forms.ValidationError("Choose a cooldown between 1 and 90 days.")
        return value

    def clean_posting_hours_text(self):
        raw = self.cleaned_data["posting_hours_text"]
        try:
            hours = sorted({int(value.strip()) for value in raw.split(",")})
        except ValueError as exc:
            raise forms.ValidationError("Enter whole hours separated by commas.") from exc
        if not hours or any(hour < 0 or hour > 23 for hour in hours):
            raise forms.ValidationError("Each posting hour must be between 0 and 23.")
        return hours

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.channels = self.cleaned_data["channels"]
        instance.posting_hours = self.cleaned_data["posting_hours_text"]
        if commit:
            instance.save()
        return instance
