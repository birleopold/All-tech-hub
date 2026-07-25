from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from catalog.models import Product, ProductImage
from catalog.responsive_images import (
    generate_responsive_variants,
    purge_responsive_name,
)
from catalog.studio_watermarks import watermark_pending_model_image


def _old_image_name(sender, instance) -> str:
    if not instance.pk:
        return ""
    return (
        sender.objects.filter(pk=instance.pk)
        .values_list("image", flat=True)
        .first()
        or ""
    )


def _prepare_image(sender, instance) -> None:
    old_name = _old_image_name(sender, instance)
    watermark_pending_model_image(instance, "image")
    current = getattr(instance, "image", None)
    current_name = getattr(current, "name", "") or ""
    if old_name and old_name != current_name:
        storage = getattr(current, "storage", None) or sender._meta.get_field("image").storage
        instance._previous_public_image = (storage, old_name)


def _after_image_save(instance) -> None:
    field_file = getattr(instance, "image", None)
    previous = getattr(instance, "_previous_public_image", None)

    def committed_work():
        if previous:
            storage, old_name = previous
            purge_responsive_name(storage, old_name)
            try:
                if storage.exists(old_name):
                    storage.delete(old_name)
            except Exception:
                pass
        if field_file and field_file.name:
            generate_responsive_variants(field_file)

    transaction.on_commit(committed_work)


def _after_image_delete(instance) -> None:
    field_file = getattr(instance, "image", None)
    if not field_file or not field_file.name:
        return
    storage = field_file.storage
    name = field_file.name

    def committed_work():
        purge_responsive_name(storage, name)
        try:
            if storage.exists(name):
                storage.delete(name)
        except Exception:
            pass

    transaction.on_commit(committed_work)


@receiver(pre_save, sender=Product)
def watermark_product_primary_image(sender, instance, **kwargs):
    _prepare_image(sender, instance)


@receiver(pre_save, sender=ProductImage)
def watermark_product_gallery_image(sender, instance, **kwargs):
    _prepare_image(sender, instance)


@receiver(post_save, sender=Product)
def generate_product_primary_responsive_images(sender, instance, **kwargs):
    _after_image_save(instance)


@receiver(post_save, sender=ProductImage)
def generate_product_gallery_responsive_images(sender, instance, **kwargs):
    _after_image_save(instance)


@receiver(post_delete, sender=Product)
def delete_product_primary_public_images(sender, instance, **kwargs):
    _after_image_delete(instance)


@receiver(post_delete, sender=ProductImage)
def delete_product_gallery_public_images(sender, instance, **kwargs):
    _after_image_delete(instance)
