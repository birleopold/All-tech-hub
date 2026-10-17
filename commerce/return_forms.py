from django import forms

from catalog.models import Product
from commerce.models import CustomerReturn


class CustomerReturnForm(forms.ModelForm):
    class Meta:
        model = CustomerReturn
        fields = ("order_line", "quantity", "reason", "disposition")
        widgets = {
            "order_line": forms.Select(attrs={"class": "form-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "reason": forms.TextInput(attrs={"class": "form-control"}),
            "disposition": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, order=None, **kwargs):
        super().__init__(*args, **kwargs)
        if order is not None:
            self.fields["order_line"].queryset = (
                order.lines.select_related("product", "product_variant")
                .filter(product__kind=Product.KIND_PHYSICAL)
            )
