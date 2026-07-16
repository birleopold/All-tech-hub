from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from catalog.models import Product, ProductImage
from catalog.responsive_images import generate_responsive_variants
from catalog.watermarks import watermark_pending_model_image


@receiver(pre_save, sender=Product)
def watermark_product_primary_image(sender, instance, **kwargs):
    watermark_pending_model_image(instance, "image")


@receiver(pre_save, sender=ProductImage)
def watermark_product_gallery_image(sender, instance, **kwargs):
    watermark_pending_model_image(instance, "image")


def _generate_after_commit(field_file) -> None:
    if not field_file or not field_file.name:
        return
    transaction.on_commit(lambda: generate_responsive_variants(field_file))


@receiver(post_save, sender=Product)
def generate_product_primary_responsive_images(sender, instance, **kwargs):
    _generate_after_commit(instance.image)


@receiver(post_save, sender=ProductImage)
def generate_product_gallery_responsive_images(sender, instance, **kwargs):
    _generate_after_commit(instance.image)
