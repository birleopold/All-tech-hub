from django import forms

from automation.models import AutomationJob


class BootstrapFormMixin:
    def apply_bootstrap(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
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
