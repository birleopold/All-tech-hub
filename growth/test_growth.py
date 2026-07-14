from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product
from commerce import cart as cart_mod
from commerce.models import Order
from core.models import CompanySettings
from growth.models import (
    Ambassador,
    AmbassadorConversion,
    ContentAsset,
    GrowthSettings,
    ProductGrowthData,
    SavedCart,
    StockAlertSubscription,
)
from growth.services import process_saved_cart_reminders, process_stock_alerts


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="sales@leosoftug.com",
)
class GrowthMarketingTests(TestCase):
    def setUp(self):
        company = CompanySettings.load()
        company.company_name = "LEOSOFT"
        company.legal_name = "LEOSOFT UG LTD"
        company.website = "https://leosoftug.com"
        company.currency_code = "UGX"
        company.default_tax_rate = Decimal("0")
        company.save()

        settings_row = GrowthSettings.load()
        settings_row.ga4_measurement_id = "G-TEST123456"
        settings_row.search_console_verification_token = "google-test-token"
        settings_row.clarity_project_id = "claritytest"
        settings_row.abandoned_cart_first_delay_hours = 1
        settings_row.abandoned_cart_second_delay_hours = 24
        settings_row.save()

        self.category = Category.objects.create(
            name="Laptops",
            slug="growth-laptops",
        )
        self.product = Product.objects.create(
            category=self.category,
            name="Growth Test Laptop",
            slug="growth-test-laptop",
            sku="LEO-GROWTH-1",
            short_description="A dependable computer for business and study.",
            price=Decimal("1000000"),
            stock_quantity=5,
            is_published=True,
        )
        self.service = Product.objects.create(
            category=self.category,
            kind=Product.KIND_SERVICE,
            name="Growth Test Repair",
            slug="growth-test-repair",
            price=Decimal("100000"),
            track_inventory=False,
            is_published=True,
        )
        self.user = get_user_model().objects.create_superuser(
            username="growth-admin",
            email="growth@example.com",
            password="TestPass123!",
        )

    def add_product_to_cart(self):
        return self.client.post(
            reverse("cart_add", args=[self.product.pk]),
            {
                "quantity": 1,
                "next": reverse("cart"),
            },
        )

    def test_verification_metadata_and_analytics_configuration_render(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="google-site-verification"')
        self.assertContains(response, "google-test-token")
        self.assertContains(response, 'data-ga4-id="G-TEST123456"')
        self.assertContains(response, 'data-clarity-id="claritytest"')
        self.assertContains(response, "analytics-consent-banner")
        self.assertContains(response, '"@type":"ComputerStore"')

    def test_product_and_cart_pages_contain_ga4_ecommerce_events(self):
        product_response = self.client.get(self.product.get_absolute_url())
        self.assertContains(product_response, "view_item")

        self.add_product_to_cart()
        cart_response = self.client.get(reverse("cart"))
        self.assertContains(cart_response, "view_cart")
        self.assertContains(cart_response, "Save and email my cart")

        checkout_response = self.client.get(reverse("checkout"))
        self.assertContains(checkout_response, "begin_checkout")

    def test_merchant_feed_excludes_services_and_contains_product_metadata(self):
        ProductGrowthData.objects.create(
            product=self.product,
            brand="Lenovo",
            gtin="1234567890123",
            mpn="82TEST",
            condition=ProductGrowthData.CONDITION_NEW,
            google_product_category="Electronics > Computers > Laptops",
        )

        response = self.client.get(reverse("marketing_product_feed_json"))
        self.assertEqual(response.status_code, 200)
        rows = response.json()["products"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], self.product.name)
        self.assertEqual(rows[0]["brand"], "Lenovo")
        self.assertEqual(rows[0]["gtin"], "1234567890123")
        self.assertEqual(rows[0]["identifier_exists"], "yes")
        self.assertNotIn(self.service.name, str(rows))

        xml_response = self.client.get(reverse("marketing_product_feed_xml"))
        self.assertContains(xml_response, "Lenovo")
        self.assertContains(xml_response, "1234567890123")
        self.assertNotContains(xml_response, self.service.name)

    def test_customer_can_save_and_restore_cart_with_explicit_consent(self):
        self.add_product_to_cart()
        response = self.client.post(
            reverse("growth_saved_cart_save"),
            {
                "name": "Test Buyer",
                "email": "buyer@example.com",
                "phone": "256700000001",
                "consent": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        saved = SavedCart.objects.get(email="buyer@example.com")
        self.assertEqual(saved.subtotal, Decimal("1000000.00"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Stop reminders", mail.outbox[0].body)

        session = self.client.session
        cart_mod.clear(session)
        session.save()
        self.assertEqual(cart_mod.get_cart(self.client.session), {})

        recovery_response = self.client.get(saved.get_recovery_path())
        self.assertEqual(recovery_response.status_code, 302)
        self.assertTrue(cart_mod.get_cart(self.client.session))

    def test_stock_alert_is_sent_after_product_becomes_available(self):
        self.product.stock_quantity = 0
        self.product.save(update_fields=["stock_quantity"])
        response = self.client.post(
            reverse("growth_stock_alert_subscribe", args=[self.product.slug]),
            {
                "email": "alerts@example.com",
                "phone": "",
                "alert_type": StockAlertSubscription.ALERT_BACK_IN_STOCK,
                "target_price": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        subscription = StockAlertSubscription.objects.get(email="alerts@example.com")
        self.assertTrue(subscription.is_active)

        self.product.stock_quantity = 3
        self.product.save(update_fields=["stock_quantity"])
        result = process_stock_alerts()

        self.assertEqual(result["sent"], 1)
        subscription.refresh_from_db()
        self.assertFalse(subscription.is_active)
        self.assertIsNotNone(subscription.notified_at)
        self.assertEqual(len(mail.outbox), 1)

    def test_cart_reminders_are_staged_not_sent_together(self):
        saved = SavedCart.objects.create(
            session_key="staged-cart-session",
            customer_name="Staged Buyer",
            email="staged@example.com",
            cart_data={f"p:{self.product.pk}": 1},
            subtotal=self.product.price,
            last_activity=timezone.now() - timedelta(days=2),
        )

        first_result = process_saved_cart_reminders()
        self.assertEqual(first_result["first"], 1)
        self.assertEqual(first_result["second"], 0)
        saved.refresh_from_db()
        self.assertIsNotNone(saved.first_reminder_sent_at)
        self.assertIsNone(saved.second_reminder_sent_at)

        saved.first_reminder_sent_at = timezone.now() - timedelta(hours=25)
        saved.save(update_fields=["first_reminder_sent_at", "updated_at"])
        second_result = process_saved_cart_reminders()
        self.assertEqual(second_result["first"], 0)
        self.assertEqual(second_result["second"], 1)
        self.assertEqual(len(mail.outbox), 2)

    def test_content_asset_generator_creates_six_channel_drafts(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("staff_growth_content_assets"),
            {
                "product": self.product.pk,
                "campaign": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContentAsset.objects.filter(product=self.product).count(), 6)
        self.assertTrue(
            ContentAsset.objects.filter(
                product=self.product,
                asset_type=ContentAsset.TYPE_TIKTOK_SCRIPT,
            ).exists()
        )

    def test_ambassador_click_checkout_and_commission_are_attributed(self):
        ambassador = Ambassador.objects.create(
            name="Campus Ambassador",
            code="campus01",
            commission_type=Ambassador.COMMISSION_PERCENT,
            commission_value=Decimal("10"),
        )
        referral = self.client.get(
            reverse("growth_ambassador_referral", args=[ambassador.code])
        )
        self.assertEqual(referral.status_code, 302)
        ambassador.refresh_from_db()
        self.assertEqual(ambassador.click_count, 1)

        self.add_product_to_cart()
        self.client.get(reverse("checkout"))
        checkout_token = self.client.session["checkout_submit_token"]
        checkout_response = self.client.post(
            reverse("checkout"),
            {
                "checkout_token": checkout_token,
                "name": "Referral Buyer",
                "email": "referral@example.com",
                "phone": "256700000002",
                "company_name": "",
                "billing_address": "Kampala, Uganda",
                "shipping_address": "Kampala, Uganda",
                "customer_note": "",
                "fulfillment_type": Order.FULFILLMENT_DELIVERY,
            },
        )
        self.assertEqual(checkout_response.status_code, 302)
        order = Order.objects.get(contact_email="referral@example.com")
        conversion = AmbassadorConversion.objects.get(order=order)
        self.assertEqual(conversion.ambassador, ambassador)
        self.assertEqual(conversion.revenue, Decimal("1000000.00"))
        self.assertEqual(conversion.commission_amount, Decimal("100000.00"))
        ambassador.refresh_from_db()
        self.assertEqual(ambassador.order_count, 1)
        self.assertEqual(ambassador.revenue_total, Decimal("1000000.00"))

    def test_growth_dashboard_requires_staff_and_loads_for_superuser(self):
        anonymous = self.client.get(reverse("staff_growth_dashboard"))
        self.assertEqual(anonymous.status_code, 302)

        self.client.force_login(self.user)
        response = self.client.get(reverse("staff_growth_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Analytics, discovery and customer recovery")
