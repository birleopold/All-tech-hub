from django import forms

from crm.models import Customer


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ("name", "company_name", "email", "phone", "tax_reference", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        duplicates = Customer.objects.filter(email__iexact=email)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError("A customer already uses this email address.")
        if self.instance.pk and self.instance.user_id:
            verified_email = self.instance.user.email.strip().lower()
            if verified_email != email:
                raise forms.ValidationError(
                    "A verified customer's email must match the linked account."
                )
        return email
