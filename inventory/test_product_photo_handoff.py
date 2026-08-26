import json
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from catalog.models import Category, Product, ProductImage
from inventory.product_photo_models import ProductPhotoSession, StaffPushSubscription


def image_upload(name="phone.jpg"):
    output = BytesIO()
    Image.new("RGB", (40, 40), "blue").save(output, format="JPEG")
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/jpeg")


class ProductPhotoHandoffTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="photographer", password="test-password", is_staff=True
        )
        category = Category.objects.create(name="Phones", slug="phones")
        self.product = Product.objects.create(
            category=category, name="Camera phone", slug="camera-phone", price="1.00"
        )
        self.client.force_login(self.staff)

    def test_staff_can_start_and_upload_to_owned_session(self):
        response = self.client.post(
            reverse("staff_product_photo_start", kwargs={"product_id": self.product.pk})
        )
        self.assertEqual(response.status_code, 200)
        session = ProductPhotoSession.objects.get(owner=self.staff)
        response = self.client.post(
            reverse("staff_product_photo_upload", kwargs={"token": session.token}),
            {"photos": [image_upload()]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProductImage.objects.filter(product=self.product).count(), 1)

    def test_other_staff_cannot_open_session(self):
        session = ProductPhotoSession.objects.create(product=self.product, owner=self.staff)
        other = get_user_model().objects.create_user(
            username="other", password="test-password", is_staff=True
        )
        self.client.force_login(other)
        response = self.client.get(
            reverse("staff_product_photo_mobile", kwargs={"token": session.token})
        )
        self.assertEqual(response.status_code, 404)

    def test_expired_session_is_rejected(self):
        session = ProductPhotoSession.objects.create(
            product=self.product,
            owner=self.staff,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        response = self.client.post(
            reverse("staff_product_photo_upload", kwargs={"token": session.token}),
            {"photos": [image_upload()]},
        )
        self.assertEqual(response.status_code, 404)

    def test_push_subscription_is_bound_to_logged_in_staff(self):
        response = self.client.post(
            reverse("staff_push_subscribe"),
            data=json.dumps({
                "endpoint": "https://push.example/subscription",
                "keys": {"p256dh": "key", "auth": "auth"},
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            StaffPushSubscription.objects.filter(user=self.staff).exists()
        )
