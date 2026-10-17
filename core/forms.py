from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from core.models import ContactMessage, SupportTicket, TicketComment

User = get_user_model()


class ContactForm(forms.ModelForm):
    REQUEST_PRODUCT = "product"
    REQUEST_QUOTE = "quote"
    REQUEST_REPAIR = "repair"
    REQUEST_INSTALLATION = "installation"
    REQUEST_SUPPORT = "support"
    REQUEST_OTHER = "other"
    REQUEST_TYPE_CHOICES = [
        (REQUEST_PRODUCT, "Product enquiry"),
        (REQUEST_QUOTE, "Formal quotation"),
        (REQUEST_REPAIR, "Repair or diagnostics"),
        (REQUEST_INSTALLATION, "Installation or setup"),
        (REQUEST_SUPPORT, "Business IT support"),
        (REQUEST_OTHER, "Other request"),
    ]

    request_type = forms.ChoiceField(
        choices=REQUEST_TYPE_CHOICES,
        label="What can we help with?",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    website = forms.CharField(
        required=False,
        label="Leave this field blank",
        widget=forms.HiddenInput(
            attrs={
                "autocomplete": "off",
                "tabindex": "-1",
                "aria-hidden": "true",
            }
        ),
    )

    class Meta:
        model = ContactMessage
        fields = ("name", "email", "phone", "subject", "message")
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Your name"}
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "you@example.com"}
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Phone or WhatsApp number",
                    "inputmode": "tel",
                }
            ),
            "subject": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "A short summary of what you need",
                }
            ),
            "message": forms.Textarea(
                attrs={
                    "rows": 6,
                    "class": "form-control",
                    "placeholder": "Include the product, device, problem, location, timeline or quantity so we can respond accurately…",
                }
            ),
        }
        help_texts = {
            "phone": "Useful for quick calls, SMS or WhatsApp follow-up in Uganda.",
            "message": "Do not include passwords, PINs or other sensitive credentials.",
        }

    field_order = (
        "request_type",
        "name",
        "email",
        "phone",
        "subject",
        "message",
        "website",
    )

    def clean(self):
        cleaned_data = super().clean()
        if (cleaned_data.get("website") or "").strip():
            raise ValidationError("Your request could not be accepted. Please try again.")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        request_type = self.cleaned_data.get("request_type", self.REQUEST_OTHER)
        request_label = dict(self.REQUEST_TYPE_CHOICES).get(
            request_type,
            "General enquiry",
        )
        instance.request_type = request_type
        subject = (instance.subject or "").strip()
        prefix = f"{request_label}: "
        if subject and not subject.lower().startswith(prefix.lower()):
            instance.subject = f"{prefix}{subject}"[:200]
        if commit:
            instance.save()
        return instance


class PortalSupportTicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = (
            "category",
            "subject",
            "description",
            "priority",
            "related_order",
            "related_job",
            "related_document",
            "related_product",
            "related_serial",
        )
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "subject": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Laptop warranty claim or invoice question",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "Describe the issue, device, error message, or document/order reference…",
                }
            ),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "related_order": forms.Select(attrs={"class": "form-select"}),
            "related_job": forms.Select(attrs={"class": "form-select"}),
            "related_document": forms.Select(attrs={"class": "form-select"}),
            "related_product": forms.Select(attrs={"class": "form-select"}),
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
        for relation in ("related_job", "related_document"):
            self.fields[relation].required = False
            self.fields[relation].empty_label = "— optional —"
            self.fields[relation].queryset = self.fields[relation].queryset.none()
        self.fields["related_product"].required = False
        self.fields["related_product"].empty_label = "— optional —"
        self.fields["related_product"].queryset = self.fields[
            "related_product"
        ].queryset.filter(is_published=True).order_by("name")
        self.fields["related_serial"].required = False
        self.fields["related_serial"].empty_label = "— optional —"
        self.fields["related_serial"].queryset = self.fields[
            "related_serial"
        ].queryset.none()
        if customer is not None:
            from billing.models import CommercialDocument
            from catalog.models import ProductSerial
            from commerce.models import Order
            from operations.models import JobCard

            self.fields["related_job"].queryset = JobCard.objects.filter(
                customer=customer
            ).order_by("-received_on")
            self.fields["related_document"].queryset = CommercialDocument.objects.filter(
                customer=customer
            ).order_by("-issue_date", "-pk")
            self.fields["related_order"].queryset = Order.objects.filter(
                customer=customer
            ).order_by("-placed_at")
            self.fields["related_serial"].queryset = ProductSerial.objects.filter(
                sold_to=customer
            ).select_related("product", "product_variant").order_by(
                "product__name",
                "serial_number",
            )
        self.fields["category"].help_text = (
            "Choose Return / RMA or Warranty claim if this relates to a purchase."
        )
        self.fields["related_serial"].help_text = (
            "Choose a purchased device when the issue is about warranty, serial number, or RMA."
        )
        self.fields["related_product"].help_text = (
            "Choose the exact product or service this support request concerns."
        )
        self.fields["related_job"].help_text = (
            "Choose your repair or installation job number, if applicable."
        )
        self.fields["related_document"].help_text = (
            "Choose your invoice, quote or other document, if applicable."
        )
        self.fields["priority"].help_text = (
            "Use High only for urgent business interruptions or serious service issues."
        )

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("category")
        serial = cleaned.get("related_serial")
        product = cleaned.get("related_product")
        order = cleaned.get("related_order")
        document = cleaned.get("related_document")
        if document is not None and order is not None and document.order_id:
            if document.order_id != order.pk:
                self.add_error(
                    "related_document",
                    "Choose a document belonging to the selected order.",
                )

        if category == SupportTicket.CATEGORY_WARRANTY and serial is None:
            self.add_error(
                "related_serial",
                "Choose the purchased device covered by this warranty claim.",
            )

        if serial is not None:
            if product is not None and product.pk != serial.product_id:
                self.add_error(
                    "related_product",
                    "The selected product does not match the selected device serial.",
                )
            elif product is None:
                cleaned["related_product"] = serial.product

            if (
                category == SupportTicket.CATEGORY_WARRANTY
                and not serial.is_under_warranty
            ):
                self.add_error(
                    "related_serial",
                    "This device no longer has active warranty coverage. "
                    "Please submit a general repair or support request.",
                )

        selected_product = cleaned.get("related_product")
        if (
            order is not None
            and selected_product is not None
            and not order.lines.filter(product_id=selected_product.pk).exists()
        ):
            self.add_error(
                "related_order",
                "The selected order does not contain the selected product.",
            )

        return cleaned


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
            "related_job",
            "related_document",
            "related_product",
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
            "related_job": forms.Select(attrs={"class": "form-select"}),
            "related_document": forms.Select(attrs={"class": "form-select"}),
            "related_product": forms.Select(attrs={"class": "form-select"}),
            "related_serial": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(
            is_staff=True
        ).order_by("username")
        self.fields["assigned_to"].required = False
        self.fields["related_product"].required = False
        self.fields["related_product"].help_text = (
            "Attach the product or service so its price and stock remain visible."
        )


class StaffSavedSearchForm(forms.Form):
    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    params = forms.CharField(widget=forms.HiddenInput())


class TicketCommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ("body", "is_internal", "attachment")
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "form-control",
                    "placeholder": "Add a reply or internal note…",
                }
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
                attrs={
                    "rows": 4,
                    "class": "form-control",
                    "placeholder": "Reply to the team…",
                }
            ),
        }
