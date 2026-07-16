from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product, ProductSerial
from crm.models import Customer


class CustomerWarrantyPortalTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="warranty-customer",
            email="warranty@example.com",
            password="strong-test-password",
        )
        self.other_user = user_model.objects.create_user(
            username="other-customer",
            email="other@example.com",
            password="strong-test-password",
        )
        self.customer = Customer.objects.create(
            name="Warranty Customer",
            email=self.user.email,
            user=self.user,
        )
        self.other_customer = Customer.objects.create(
            name="Other Customer",
            email=self.other_user.email,
            user=self.other_user,
        )
        category = Category.objects.create(name="Computers", slug="computers")
        self.product = Product.objects.create(
            category=category,
            name="Warranty Laptop",
            slug="warranty-laptop",
            price="1500000.00",
            stock_quantity=1,
        )
        self.active = ProductSerial.objects.create(
            product=self.product,
            serial_number="ACTIVE-SERIAL-001",
            status=ProductSerial.STATUS_SOLD,
            sold_to=self.customer,
            sold_at=date.today(),
            warranty_months=12,
        )
        self.expired = ProductSerial.objects.create(
            product=self.product,
            serial_number="EXPIRED-SERIAL-002",
            status=ProductSerial.STATUS_SOLD,
            sold_to=self.customer,
            sold_at=date(2020, 1, 1),
            warranty_months=12,
        )
        ProductSerial.objects.create(
            product=self.product,
            serial_number="OTHER-SERIAL-003",
            status=ProductSerial.STATUS_SOLD,
            sold_to=self.other_customer,
            sold_at=date.today(),
            warranty_months=12,
        )

    def test_warranty_centre_is_private_and_customer_scoped(self):
        response = self.client.get(reverse("portal_warranties"))
        self.assertRedirects(
            response,
            f"{reverse('portal_login')}?next={reverse('portal_warranties')}",
            fetch_redirect_response=False,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("portal_warranties"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.active.serial_number)
        self.assertContains(response, self.expired.serial_number)
        self.assertNotContains(response, "OTHER-SERIAL-003")
        self.assertContains(response, 'name="robots" content="noindex,nofollow,noarchive"')
        self.assertEqual(response.context["active_warranty_count"], 1)
        self.assertEqual(response.context["expired_warranty_count"], 1)

    def test_portal_home_displays_active_warranty_count(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("portal_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Active warranties")
        self.assertContains(response, reverse("portal_warranties"))
