from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product
from commerce.forms import CheckoutForm
from commerce.models import CustomerReturn, Order, OrderLine, OrderStatusEvent
from crm.models import Customer
from loyalty.models import (
    CustomerMarketingPreference,
    LoyaltyAccount,
    LoyaltyTransaction,
    MarketingConsentEvent,
)
from loyalty.reporting import consent_integrity_findings, customer_growth_summary
from loyalty.services import award_completed_order_points


@override_settings(
    ORDER_CUSTOMER_EMAILS_ENABLED=False,
    ORDER_REVIEW_EMAILS_ENABLED=False,
    LOYALTY_POINTS_ENABLED=True,
    LOYALTY_SPEND_PER_POINT=10000,
    LOYALTY_SILVER_POINTS=100,
    LOYALTY_GOLD_POINTS=500,
    LOYALTY_PLATINUM_POINTS=1500,
)
class ConsentAndLoyaltyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="loyalty-customer",
            email="customer@example.com",
            password="strong-test-password",
        )
        self.customer = Customer.objects.create(
            name="Loyal Customer",
            email="customer@example.com",
            phone="+256700000001",
            user=self.user,
        )
        self.category = Category.objects.create(
            name="Loyalty products",
            slug="loyalty-products",
        )
        self.product = Product.objects.create(
            category=self.category,
            name="Loyalty Laptop",
            slug="loyalty-laptop",
            price="1200000.00",
            stock_quantity=5,
            kind=Product.KIND_PHYSICAL,
        )
        self.order = Order.objects.create(
            reference="ORD-LOYALTY-001",
            customer=self.customer,
            status=Order.STATUS_DELIVERED,
            contact_name=self.customer.name,
            contact_email=self.customer.email,
            contact_phone=self.customer.phone,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            total="1200000.00",
        )
        self.line = OrderLine.objects.create(
            order=self.order,
            product=self.product,
            description=self.product.name,
            quantity=1,
            unit_price=self.product.price,
        )

    def test_checkout_consent_is_explicit_and_persisted(self):
        form = CheckoutForm(
            {
                "name": "Consent Customer",
                "email": "consent@example.com",
                "phone": "+256700000002",
                "billing_address": "Kampala",
                "shipping_address": "Kampala",
                "fulfillment_type": Order.FULFILLMENT_PICKUP,
                "marketing_email_opt_in": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        customer = form.save_customer()
        preference = customer.marketing_preference
        event = MarketingConsentEvent.objects.get(preference=preference)
        self.assertTrue(preference.email_marketing)
        self.assertFalse(preference.whatsapp_marketing)
        self.assertTrue(preference.product_updates)
        self.assertTrue(preference.special_offers)
        self.assertIsNotNone(preference.consented_at)
        self.assertEqual(
            preference.consent_source,
            CustomerMarketingPreference.SOURCE_CHECKOUT,
        )
        self.assertEqual(event.action, MarketingConsentEvent.ACTION_GRANTED)
        self.assertTrue(event.email_marketing)

    def test_unchecked_checkout_does_not_create_or_withdraw_consent(self):
        existing = CustomerMarketingPreference.objects.create(
            customer=self.customer,
            email_marketing=True,
            product_updates=True,
            special_offers=True,
            consent_source=CustomerMarketingPreference.SOURCE_PORTAL,
        )
        form = CheckoutForm(
            {
                "name": self.customer.name,
                "email": self.customer.email,
                "phone": self.customer.phone,
                "billing_address": "Kampala",
                "shipping_address": "Kampala",
                "fulfillment_type": Order.FULFILLMENT_PICKUP,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save_customer()
        existing.refresh_from_db()
        self.assertTrue(existing.email_marketing)
        self.assertIsNone(existing.withdrawn_at)
        self.assertEqual(MarketingConsentEvent.objects.count(), 0)

    def test_portal_preferences_are_private_and_customer_controlled(self):
        self.client.force_login(self.user)
        url = reverse("portal_marketing_preferences")
        response = self.client.post(
            url,
            {
                "email_marketing": "on",
                "product_updates": "on",
                "special_offers": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        preference = self.customer.marketing_preference
        event = MarketingConsentEvent.objects.get(preference=preference)
        self.assertTrue(preference.email_marketing)
        self.assertEqual(
            preference.consent_source,
            CustomerMarketingPreference.SOURCE_PORTAL,
        )
        self.assertEqual(event.action, MarketingConsentEvent.ACTION_GRANTED)
        self.assertIn("private", response.headers["Cache-Control"])
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn("noindex", response.headers["X-Robots-Tag"])

    def test_unsubscribe_get_is_safe_and_post_withdraws_all(self):
        preference = CustomerMarketingPreference.objects.create(
            customer=self.customer,
            email_marketing=True,
            whatsapp_marketing=True,
            product_updates=True,
            special_offers=True,
        )
        url = reverse(
            "marketing_unsubscribe_all",
            kwargs={"token": preference.unsubscribe_token},
        )
        get_response = self.client.get(url)
        preference.refresh_from_db()
        self.assertEqual(get_response.status_code, 200)
        self.assertTrue(preference.email_marketing)
        self.assertEqual(MarketingConsentEvent.objects.count(), 0)

        post_response = self.client.post(url)
        preference.refresh_from_db()
        event = MarketingConsentEvent.objects.get(preference=preference)
        self.assertEqual(post_response.status_code, 200)
        self.assertFalse(preference.email_marketing)
        self.assertFalse(preference.whatsapp_marketing)
        self.assertFalse(preference.product_updates)
        self.assertFalse(preference.special_offers)
        self.assertIsNotNone(preference.withdrawn_at)
        self.assertEqual(event.action, MarketingConsentEvent.ACTION_WITHDRAWN)
        self.assertEqual(post_response.headers["Cache-Control"], "private, no-store")
        self.assertNotContains(post_response, self.customer.email)

    def test_completed_order_awards_points_once_and_sets_tier(self):
        first = award_completed_order_points(self.order)
        second = award_completed_order_points(self.order)
        account = LoyaltyAccount.objects.get(customer=self.customer)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(account.points_balance, 120)
        self.assertEqual(account.lifetime_points, 120)
        self.assertEqual(account.tier, LoyaltyAccount.TIER_SILVER)
        self.assertEqual(LoyaltyTransaction.objects.count(), 1)

    def test_returned_order_does_not_earn_points(self):
        CustomerReturn.objects.create(
            reference="RET-LOYALTY-001",
            order_line=self.line,
            quantity=1,
            reason="Returned during test",
            disposition=CustomerReturn.DISPOSITION_RESTOCK,
            processed_by=None,
        )
        self.assertIsNone(award_completed_order_points(self.order))
        self.assertFalse(LoyaltyAccount.objects.filter(customer=self.customer).exists())

    def test_terminal_status_event_awards_after_commit(self):
        second_order = Order.objects.create(
            reference="ORD-LOYALTY-002",
            customer=self.customer,
            status=Order.STATUS_FULFILLED,
            contact_name=self.customer.name,
            contact_email=self.customer.email,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            total="500000.00",
        )
        with self.captureOnCommitCallbacks(execute=True):
            OrderStatusEvent.objects.create(
                order=second_order,
                from_status=Order.STATUS_READY,
                to_status=Order.STATUS_FULFILLED,
                visible_to_customer=False,
            )
        account = LoyaltyAccount.objects.get(customer=self.customer)
        self.assertEqual(account.points_balance, 50)
        self.assertTrue(
            LoyaltyTransaction.objects.filter(
                idempotency_key=f"order:{second_order.pk}:completed"
            ).exists()
        )

    def test_audience_requires_channel_and_topic_consent(self):
        preference = CustomerMarketingPreference.objects.create(
            customer=self.customer,
            email_marketing=True,
            product_updates=True,
            special_offers=False,
        )
        MarketingConsentEvent.objects.create(
            preference=preference,
            customer=self.customer,
            action=MarketingConsentEvent.ACTION_GRANTED,
            source=CustomerMarketingPreference.SOURCE_PORTAL,
            email_marketing=True,
            product_updates=True,
            consent_text_version=preference.consent_text_version,
        )
        other = Customer.objects.create(
            name="Dormant Without Consent",
            email="no-consent@example.com",
        )
        Order.objects.create(
            reference="ORD-NO-CONSENT",
            customer=other,
            status=Order.STATUS_FULFILLED,
            contact_name=other.name,
            contact_email=other.email,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            total="900000.00",
        )
        product_summary = customer_growth_summary(
            channel="email",
            topic="product_updates",
            segment="all",
        )
        product_ids = {customer.pk for customer in product_summary["audience"]}
        self.assertIn(self.customer.pk, product_ids)
        self.assertNotIn(other.pk, product_ids)

        offer_summary = customer_growth_summary(
            channel="email",
            topic="special_offers",
            segment="all",
        )
        offer_ids = {customer.pk for customer in offer_summary["audience"]}
        self.assertNotIn(self.customer.pk, offer_ids)
        preference.special_offers = True
        preference.save()
        offer_summary = customer_growth_summary(
            channel="email",
            topic="special_offers",
            segment="all",
        )
        self.assertIn(
            self.customer.pk,
            {customer.pk for customer in offer_summary["audience"]},
        )

    def test_integrity_audit_detects_loyalty_balance_mismatch(self):
        account = LoyaltyAccount.objects.create(
            customer=self.customer,
            points_balance=10,
            lifetime_points=10,
        )
        LoyaltyTransaction.objects.create(
            account=account,
            kind=LoyaltyTransaction.KIND_EARN,
            points_delta=5,
            idempotency_key="manual-test-mismatch",
        )
        findings = consent_integrity_findings()
        self.assertEqual(findings["loyalty_balance_mismatch_count"], 1)
        self.assertGreater(findings["errors"], 0)

    def test_staff_growth_dashboard_requires_staff(self):
        url = reverse("staff_customer_growth_dashboard")
        self.assertNotEqual(self.client.get(url).status_code, 200)
        staff = get_user_model().objects.create_user(
            username="growth-staff",
            password="strong-test-password",
            is_staff=True,
        )
        self.client.force_login(staff)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer growth and loyalty")
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
