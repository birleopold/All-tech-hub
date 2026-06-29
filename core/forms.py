from django import forms
from django.contrib.auth import get_user_model

from core.models import ContactMessage, SupportTicket, TicketComment

User = get_user_model()


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ("name", "email", "phone", "subject", "message")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Your name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@example.com"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Phone or WhatsApp number"}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "What do you need help with?"}),
            "message": forms.Textarea(attrs={"rows": 5, "class": "form-control", "placeholder": "Share product, repair, installation or support details…"}),
        }
        help_texts = {
            "phone": "Useful for quick calls, SMS or WhatsApp follow-up in Uganda.",
        }


class PortalSupportTicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ("category", "subject", "description", "priority", "related_order", "related_serial")
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Laptop warranty claim or invoice question"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5, "placeholder": "Describe the issue, device, error message, or document/order reference…"}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "related_order": forms.Select(attrs={"class": "form-select"}),
            "related_serial": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["priority"].choices = [
            (SupportTicket.PRIORITY_LOW, "Low"),
            (SupportTicket.PRIORITY_NORMAL, "Normal"),
            (SupportTicket.PRIORITY_HIGH, "High"),
        ]
        self.fields["related_order"].required = False
        self.fields["related_order"].empty_label = "— optional —"
        self.fields["related_serial"].required = False
        self.fields["related_serial"].empty_label = "— optional —"
        self.fields["related_serial"].queryset = self.fields["related_serial"].queryset.none()
        if customer is not None:
            from catalog.models import ProductSerial
            from commerce.models import Order

            self.fields["related_order"].queryset = Order.objects.filter(
                customer=customer
            ).order_by("-placed_at")
            self.fields["related_serial"].queryset = ProductSerial.objects.filter(
                sold_to=customer
            ).select_related("product", "product_variant").order_by("product__name", "serial_number")
        self.fields["category"].help_text = (
            "Choose Return / RMA or Warranty claim if this relates to a purchase."
        )
        self.fields["related_serial"].help_text = (
            "Choose a purchased device when the issue is about warranty, serial number, or RMA."
        )
        self.fields["priority"].help_text = (
            "Use High only for urgent business interruptions or serious service issues."
        )


class StaffSupportTicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = (
            "customer",
            "category",
            "subject",
            "description",
            "status",
            "priority",
            "assigned_to",
            "related_order",
            "related_serial",
        )
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "subject": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "assigned_to": forms.Select(attrs={"class": "form-select"}),
            "related_order": forms.Select(attrs={"class": "form-select"}),
            "related_serial": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(
            is_staff=True
        ).order_by("username")
        self.fields["assigned_to"].required = False


class StaffSavedSearchForm(forms.Form):
    name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={"class": "form-control"}))
    params = forms.CharField(widget=forms.HiddenInput())


class TicketCommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ("body", "is_internal", "attachment")
        widgets = {
            "body": forms.Textarea(
                attrs={"rows": 3, "class": "form-control", "placeholder": "Add a reply or internal note…"}
            ),
            "is_internal": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "attachment": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }


class PortalTicketReplyForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ("body",)
        widgets = {
            "body": forms.Textarea(
                attrs={"rows": 4, "class": "form-control", "placeholder": "Reply to the team…"}
            ),
        }
