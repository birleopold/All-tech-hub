from django.db.models.signals import pre_save
from django.dispatch import receiver

from catalog.models import Product, ProductImage
from catalog.watermarks import watermark_pending_model_image


@receiver(pre_save, sender=Product)
def watermark_product_primary_image(sender, instance, **kwargs):
    watermark_pending_model_image(instance, "image")


@receiver(pre_save, sender=ProductImage)
def watermark_product_gallery_image(sender, instance, **kwargs):
    watermark_pending_model_image(instance, "image")
