import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def default_photo_session_expiry():
    return timezone.now() + timedelta(hours=24)


class ProductPhotoSession(models.Model):
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="photo_sessions"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_photo_sessions",
    )
    token = models.CharField(max_length=64, unique=True, db_index=True, editable=False)
    expires_at = models.DateTimeField(default=default_photo_session_expiry, db_index=True)
    last_upload_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.closed_at is None and self.expires_at > timezone.now()

    def __str__(self):
        return f"Photos for {self.product} ({self.owner})"


class StaffPushSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-last_used_at",)

    def __str__(self):
        return f"Push device for {self.user}"
