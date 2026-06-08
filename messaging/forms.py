from django import forms


class SendEmailForm(forms.Form):
    to_email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))
    subject = forms.CharField(max_length=200, widget=forms.TextInput(attrs={"class": "form-control"}))
    body = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )
    attach_pdf = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

