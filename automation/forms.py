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
        label="Where should posts be published?",
        choices=CHANNEL_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select one or more channels. Only channels marked Connected can publish.",
    )
    posting_hours_text = forms.CharField(
        label="Daily posting times",
        help_text=(
            "Enter Kampala-local hours separated by commas. "
            "Use 9 for one daily post or 9,18 for two."
        ),
    )

    class Meta:
        model = SocialAutopilotSettings
        fields = (
            "enabled",
            "mode",
            "channels",
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
        self.fields["mode"].label = "How should publishing work?"
        self.fields["queue_days"].label = "How many days should be prepared?"
        self.fields["queue_days"].help_text = (
            "The system keeps this many upcoming days ready and replenishes them automatically."
        )
        self.fields["product_cooldown_days"].label = "Days before repeating a product"
        self.fields["include_prices"].label = "Include product prices"
        self.fields["require_in_stock"].label = "Only promote products currently in stock"
        self.fields["default_hashtags"].label = "Default hashtags"
        self.fields["preferred_product"].label = "Feature one product first (optional)"
        self.fields["preferred_product"].help_text = (
            "Leave blank for automatic product selection. A chosen product is used once, then cleared."
        )
        self.apply_bootstrap()

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
        if len(hours) > 4:
            raise forms.ValidationError("Choose no more than four posting times each day.")
        return hours

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.channels = self.cleaned_data["channels"]
        instance.posting_hours = self.cleaned_data["posting_hours_text"]
        instance.posts_per_day = len(instance.posting_hours)
        if commit:
            instance.save()
        return instance
