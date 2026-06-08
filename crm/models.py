from django.conf import settings
from django.db import models
from django.utils import timezone


class Customer(models.Model):
    name = models.CharField(max_length=200)
    company_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=64, blank=True)
    tax_reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_profile",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        if self.company_name:
            return f"{self.name} ({self.company_name})"
        return self.name


class CustomerAddress(models.Model):
    KIND_SHIPPING = "shipping"
    KIND_BILLING = "billing"
    KIND_BOTH = "both"
    KIND_CHOICES = [
        (KIND_SHIPPING, "Shipping"),
        (KIND_BILLING, "Billing"),
        (KIND_BOTH, "Shipping & billing"),
    ]

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="addresses"
    )
    label = models.CharField(max_length=64, default="Primary")
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=KIND_BOTH)
    contact_name = models.CharField(max_length=200, blank=True)
    contact_phone = models.CharField(max_length=64, blank=True)
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=120)
    region = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    country = models.CharField(max_length=120, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Customer addresses"
        ordering = ["-is_default", "label"]

    def __str__(self) -> str:
        return f"{self.label} — {self.line1}, {self.city}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            CustomerAddress.objects.filter(customer=self.customer).exclude(
                pk=self.pk
            ).update(is_default=False)

    def as_text(self) -> str:
        parts = [self.line1]
        if self.line2:
            parts.append(self.line2)
        loc = ", ".join(
            x for x in [self.city, self.region, self.postal_code] if x
        )
        if loc:
            parts.append(loc)
        if self.country:
            parts.append(self.country)
        return "\n".join(parts)
