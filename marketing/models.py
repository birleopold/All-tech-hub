from django.db import models


class SocialProfileSettings(models.Model):
    """Singleton social-profile links used across the public website."""

    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)
    x_url = models.URLField(blank=True, verbose_name="X / Twitter URL")
    linkedin_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    whatsapp_number = models.CharField(
        max_length=32,
        blank=True,
        help_text="Include the country code and digits only, for example 256700000000.",
    )
    default_share_message = models.CharField(
        max_length=240,
        blank=True,
        help_text="Optional short message added to product and service sharing text.",
    )

    class Meta:
        verbose_name = "Social media settings"
        verbose_name_plural = "Social media settings"

    def __str__(self) -> str:
        return "Social media settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SocialProfileSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def whatsapp_url(self) -> str:
        digits = "".join(ch for ch in self.whatsapp_number if ch.isdigit())
        return f"https://wa.me/{digits}" if digits else ""
