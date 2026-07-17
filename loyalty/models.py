from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class CustomerMarketingPreference(models.Model):
    SOURCE_CHECKOUT = "checkout"
    SOURCE_PORTAL = "portal"
    SOURCE_STAFF = "staff"
    SOURCE_IMPORT = "import"
    SOURCE_CHOICES = [
        (SOURCE_CHECKOUT, "Checkout"),
        (SOURCE_PORTAL, "Customer portal"),
        (SOURCE_STAFF, "Staff recorded"),
        (SOURCE_IMPORT, "Verified import"),
    ]

    customer = models.OneToOneField(
        "crm.Customer",
        on_delete=models.CASCADE,
        related_name="marketing_preference",
    )
    email_marketing = models.BooleanField(default=False)
    whatsapp_marketing = models.BooleanField(default=False)
    product_updates = models.BooleanField(default=False)
    special_offers = models.BooleanField(default=False)
    consent_source = models.CharField(
        max_length=16,
        choices=SOURCE_CHOICES,
        default=SOURCE_PORTAL,
    )
    consent_text_version = models.CharField(max_length=32, default="2026-07")
    consented_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    unsubscribe_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["customer__name", "customer_id"]

    def __str__(self) -> str:
        return f"Marketing preferences — {self.customer}"

    @property
    def has_any_consent(self) -> bool:
        return self.email_marketing or self.whatsapp_marketing

    def save(self, *args, **kwargs):
        previous_had_consent = False
        previous_withdrawn_at = None
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                "email_marketing",
                "whatsapp_marketing",
                "withdrawn_at",
            ).first()
            if previous:
                previous_had_consent = bool(
                    previous["email_marketing"] or previous["whatsapp_marketing"]
                )
                previous_withdrawn_at = previous["withdrawn_at"]

        if not self.has_any_consent:
            self.product_updates = False
            self.special_offers = False
            if previous_had_consent and self.withdrawn_at is None:
                self.withdrawn_at = timezone.now()
            elif not previous_had_consent and self.withdrawn_at is None:
                self.withdrawn_at = previous_withdrawn_at
        else:
            if (
                self.consented_at is None
                or previous_withdrawn_at is not None
                or not previous_had_consent
            ):
                self.consented_at = timezone.now()
            self.withdrawn_at = None
        super().save(*args, **kwargs)


class MarketingConsentEvent(models.Model):
    ACTION_GRANTED = "granted"
    ACTION_UPDATED = "updated"
    ACTION_WITHDRAWN = "withdrawn"
    ACTION_CHOICES = [
        (ACTION_GRANTED, "Consent granted"),
        (ACTION_UPDATED, "Preferences updated"),
        (ACTION_WITHDRAWN, "Consent withdrawn"),
    ]

    preference = models.ForeignKey(
        CustomerMarketingPreference,
        on_delete=models.CASCADE,
        related_name="events",
    )
    customer = models.ForeignKey(
        "crm.Customer",
        on_delete=models.CASCADE,
        related_name="marketing_consent_events",
    )
    action = models.CharField(max_length=16, choices=ACTION_CHOICES, db_index=True)
    source = models.CharField(
        max_length=16,
        choices=CustomerMarketingPreference.SOURCE_CHOICES,
    )
    email_marketing = models.BooleanField(default=False)
    whatsapp_marketing = models.BooleanField(default=False)
    product_updates = models.BooleanField(default=False)
    special_offers = models.BooleanField(default=False)
    consent_text_version = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.customer} — {self.get_action_display()}"


class LoyaltyAccount(models.Model):
    TIER_MEMBER = "member"
    TIER_SILVER = "silver"
    TIER_GOLD = "gold"
    TIER_PLATINUM = "platinum"
    TIER_CHOICES = [
        (TIER_MEMBER, "Member"),
        (TIER_SILVER, "Silver"),
        (TIER_GOLD, "Gold"),
        (TIER_PLATINUM, "Platinum"),
    ]

    customer = models.OneToOneField(
        "crm.Customer",
        on_delete=models.CASCADE,
        related_name="loyalty_account",
    )
    points_balance = models.PositiveIntegerField(default=0)
    lifetime_points = models.PositiveIntegerField(default=0)
    tier = models.CharField(
        max_length=16,
        choices=TIER_CHOICES,
        default=TIER_MEMBER,
        db_index=True,
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-lifetime_points", "customer__name"]

    def __str__(self) -> str:
        return f"{self.customer} — {self.get_tier_display()}"


class LoyaltyTransaction(models.Model):
    KIND_EARN = "earn"
    KIND_ADJUST = "adjust"
    KIND_REVERSE = "reverse"
    KIND_CHOICES = [
        (KIND_EARN, "Points earned"),
        (KIND_ADJUST, "Staff adjustment"),
        (KIND_REVERSE, "Points reversed"),
    ]

    account = models.ForeignKey(
        LoyaltyAccount,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    points_delta = models.IntegerField()
    idempotency_key = models.CharField(max_length=180, unique=True, db_index=True)
    order_reference = models.CharField(max_length=32, blank=True, db_index=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(points_delta=0),
                name="loyalty_points_delta_nonzero",
            )
        ]

    def __str__(self) -> str:
        sign = "+" if self.points_delta > 0 else ""
        return f"{self.account.customer}: {sign}{self.points_delta}"
