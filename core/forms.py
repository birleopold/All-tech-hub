from django import forms
from django.contrib.auth import get_user_model

from core.models import ContactMessage, SupportTicket, TicketComment

User = get_user_model()


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ("name", "email", "phone", "subject", "message")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "subject": forms.TextInput(attrs={"class": "form-control"}),
            "message": forms.Textarea(attrs={"rows": 5, "class": "form-control"}),
        }


class PortalSupportTicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ("category", "subject", "description", "priority", "related_order")
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "subject": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "related_order": forms.Select(attrs={"class": "form-select"}),
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
        if customer is not None:
            from commerce.models import Order

            self.fields["related_order"].queryset = Order.objects.filter(
                customer=customer
            ).order_by("-placed_at")
        self.fields["category"].help_text = (
            "Choose Return / RMA or Warranty claim if this relates to a purchase."
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
