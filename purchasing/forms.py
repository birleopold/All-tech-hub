from django import forms

from purchasing.models import SupplierReturn


class SupplierReturnForm(forms.ModelForm):
    class Meta:
        model = SupplierReturn
        fields = ("purchase_line", "quantity", "reason")
        widgets = {
            "purchase_line": forms.Select(attrs={"class": "form-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "reason": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, purchase_order=None, **kwargs):
        super().__init__(*args, **kwargs)
        if purchase_order is not None:
            self.fields["purchase_line"].queryset = purchase_order.lines.select_related(
                "product", "product_variant"
            )
