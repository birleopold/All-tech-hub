from django import forms

from commerce.models import Order, Shipment


class OrderStatusForm(forms.Form):
    status = forms.ChoiceField(
        choices=Order.STATUS_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    note = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )


class ShipmentForm(forms.ModelForm):
    class Meta:
        model = Shipment
        fields = (
            "carrier",
            "tracking_number",
            "tracking_url",
            "status",
            "estimated_delivery",
            "note",
        )
        widgets = {
            "carrier": forms.TextInput(attrs={"class": "form-control"}),
            "tracking_number": forms.TextInput(attrs={"class": "form-control"}),
            "tracking_url": forms.URLInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "estimated_delivery": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "note": forms.TextInput(attrs={"class": "form-control"}),
        }
