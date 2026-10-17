from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from billing.models import CommercialDocument
from catalog.models import Category, Product
from commerce.forms import CheckoutForm
from commerce.models import Order
from core.models import CompanySettings
from crm.models import Customer
from merchandising.models import DeliveryZone


class CheckoutDeliveryAndIdentityTests(TestCase):
    def setUp(self):
        self.zone = DeliveryZone.objects.create(
            name="Central Kampala",
            areas="Kololo, Nakasero and Kampala Road",
            fee_from=Decimal("15000.00"),
            lead_time="Same day",
        )
        self.base_data = {
            "name": "Customer",
            "email": "buyer@example.com",
            "phone": "0700000000",
            "company_name": "",
            "billing_address": "Plot 1, Kampala",
            "shipping_address": "",
            "customer_note": "",
            "fulfillment_type": Order.FULFILLMENT_DELIVERY,
        }

    def test_delivery_requires_an_available_zone(self):
        form = CheckoutForm(data=self.base_data)
        self.assertFalse(form.is_valid())
        self.assertIn("delivery_zone", form.errors)

    def test_selected_delivery_zone_supplies_the_delivery_fee(self):
        form = CheckoutForm(data={**self.base_data, "delivery_zone": self.zone.pk})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.delivery_fee, Decimal("15000.00"))

    def test_no_delivery_zones_disables_delivery_without_inventing_zero_shipping(self):
        self.zone.is_active = False
        self.zone.save(update_fields=["is_active"])
        form = CheckoutForm(data=self.base_data)
        self.assertFalse(form.is_valid())
        self.assertIn("fulfillment_type", form.errors)
        pickup = CheckoutForm(
            data={**self.base_data, "fulfillment_type": Order.FULFILLMENT_PICKUP}
        )
        self.assertTrue(pickup.is_valid(), pickup.errors)
        self.assertEqual(pickup.delivery_fee, Decimal("0.00"))
        self.assertEqual(
            list(CheckoutForm().fields["fulfillment_type"].choices),
            [(Order.FULFILLMENT_PICKUP, "Pickup")],
        )

    def test_store_pickup_does_not_add_delivery_fee(self):
        form = CheckoutForm(
            data={
                **self.base_data,
                "fulfillment_type": Order.FULFILLMENT_PICKUP,
                "delivery_zone": self.zone.pk,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.delivery_fee, Decimal("0.00"))
        self.assertIsNone(form.cleaned_data["delivery_zone"])

    def test_guest_checkout_cannot_overwrite_existing_customer_identity(self):
        customer = Customer.objects.create(
            name="Verified original", email="buyer@example.com", phone="original"
        )
        form = CheckoutForm(
            data={
                **self.base_data,
                "name": "Untrusted replacement",
                "phone": "replacement",
                "delivery_zone": self.zone.pk,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save_customer().pk, customer.pk)
        customer.refresh_from_db()
        self.assertEqual(customer.name, "Verified original")
        self.assertEqual(customer.phone, "original")

    def test_checkout_and_invoice_keep_delivery_and_tax_in_sync(self):
        company = CompanySettings.load()
        company.default_tax_rate = Decimal("18.00")
        company.save(update_fields=["default_tax_rate"])
        category = Category.objects.create(name="Laptops", slug="delivery-laptops")
        product = Product.objects.create(
            category=category,
            name="Business laptop",
            slug="delivery-business-laptop",
            price=Decimal("100000.00"),
            stock_quantity=2,
        )
        self.client.post(reverse("cart_add", args=[product.pk]), {"quantity": "1"})
        checkout = self.client.get(reverse("checkout"))
        self.assertEqual(checkout.status_code, 200)
        token = self.client.session["checkout_submit_token"]
        response = self.client.post(
            reverse("checkout"),
            {
                **self.base_data,
                "delivery_zone": self.zone.pk,
                "checkout_token": token,
            },
        )
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.delivery_fee, Decimal("15000.00"))
        self.assertEqual(order.tax_amount, Decimal("20700.00"))
        self.assertEqual(order.total, Decimal("135700.00"))

        staff = get_user_model().objects.create_user(
            username="invoice-staff", password="staff-password", is_staff=True
        )
        self.client.force_login(staff)
        invoice_response = self.client.post(
            reverse("staff_order_invoice", args=[order.pk])
        )
        self.assertEqual(invoice_response.status_code, 302)
        invoice = CommercialDocument.objects.get(order=order)
        self.assertEqual(invoice.shipping_amount, order.delivery_fee)
        self.assertEqual(invoice.tax_amount, order.tax_amount)
        self.assertEqual(invoice.total, order.total)
