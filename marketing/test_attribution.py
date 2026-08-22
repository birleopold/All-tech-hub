from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product
from commerce.models import Order
from growth.models import Ambassador, AmbassadorConversion, SavedCart
from growth.services import AMBASSADOR_SESSION_KEY
from marketing.attribution import SESSION_ATTRIBUTION_KEY, order_attribution
from marketing.models import CampaignLink, MarketingCampaign


class CampaignOrderAttributionTests(TestCase):
    def setUp(self):
        self.campaign = MarketingCampaign.objects.create(
            name="Kampala laptop sale",
            budget=Decimal("200000.00"),
        )
        self.link = CampaignLink.objects.create(
            campaign=self.campaign,
            name="TikTok laptop demo",
            destination_url="https://testserver/",
            source="tiktok",
            medium="social",
            content="laptop-demo",
        )

    def test_tracked_click_records_expiring_attribution(self):
        response = self.client.get(reverse("marketing_track", args=[self.link.code]))

        self.assertEqual(response.status_code, 302)
        attribution = self.client.session[SESSION_ATTRIBUTION_KEY]
        self.assertEqual(attribution["link_id"], self.link.pk)
        self.assertIn("clicked_at", attribution)

    def test_new_campaign_click_supersedes_older_ambassador_referral(self):
        ambassador = Ambassador.objects.create(name="Previous creator", code="previous")
        self.client.get(reverse("growth_ambassador_referral", args=[ambassador.code]))
        self.assertIn(AMBASSADOR_SESSION_KEY, self.client.session)

        self.client.get(reverse("marketing_track", args=[self.link.code]))

        self.assertNotIn(AMBASSADOR_SESSION_KEY, self.client.session)
        self.assertEqual(
            self.client.session[SESSION_ATTRIBUTION_KEY]["link_id"], self.link.pk
        )

    def test_attribution_uses_database_link_not_tampered_session_labels(self):
        values = order_attribution(
            {
                SESSION_ATTRIBUTION_KEY: {
                    "link_id": self.link.pk,
                    "source": "forged-source",
                    "clicked_at": timezone.now().isoformat(),
                }
            }
        )

        self.assertEqual(values["marketing_source"], "tiktok")
        self.assertEqual(values["marketing_campaign"], self.campaign.slug)
        self.assertEqual(values["marketing_link"], self.link)

    @override_settings(MARKETING_ATTRIBUTION_WINDOW_DAYS=7)
    def test_expired_click_cannot_claim_later_order(self):
        values = order_attribution(
            {
                SESSION_ATTRIBUTION_KEY: {
                    "link_id": self.link.pk,
                    "clicked_at": (timezone.now() - timedelta(days=8)).isoformat(),
                }
            }
        )

        self.assertEqual(values, {})

    def test_future_or_invalid_click_cannot_claim_order(self):
        for clicked_at in [
            (timezone.now() + timedelta(hours=1)).isoformat(),
            "invalid",
            "2026-08-01T12:00:00",
        ]:
            with self.subTest(clicked_at=clicked_at):
                self.assertEqual(
                    order_attribution(
                        {
                            SESSION_ATTRIBUTION_KEY: {
                                "link_id": self.link.pk,
                                "clicked_at": clicked_at,
                            }
                        }
                    ),
                    {},
                )

    def test_checkout_persists_and_consumes_last_click(self):
        category = Category.objects.create(name="Laptops", slug="attribution-laptops")
        product = Product.objects.create(
            category=category,
            name="Business laptop",
            slug="attribution-business-laptop",
            price=Decimal("1500000.00"),
            stock_quantity=2,
            is_published=True,
        )
        self.client.get(reverse("marketing_track", args=[self.link.code]))
        self.client.post(reverse("cart_add", kwargs={"product_id": product.pk}), {"quantity": 1})
        self.client.get(reverse("checkout"))
        token = self.client.session["checkout_submit_token"]

        response = self.client.post(
            reverse("checkout"),
            {
                "name": "TikTok buyer",
                "email": "tiktok-buyer@example.com",
                "phone": "0700000000",
                "company_name": "",
                "billing_address": "Kampala",
                "shipping_address": "",
                "customer_note": "",
                "fulfillment_type": Order.FULFILLMENT_PICKUP,
                "checkout_token": token,
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.marketing_link, self.link)
        self.assertEqual(order.marketing_source, "tiktok")
        self.assertEqual(order.marketing_medium, "social")
        self.assertEqual(order.marketing_campaign, self.campaign.slug)
        self.assertNotIn(SESSION_ATTRIBUTION_KEY, self.client.session)

    def test_ambassador_checkout_credits_referral_and_recovers_saved_cart(self):
        ambassador = Ambassador.objects.create(
            name="Trusted creator",
            code="trusted-creator",
            commission_value=Decimal("10.00"),
        )
        category = Category.objects.create(name="Referral laptops", slug="referral-laptops")
        product = Product.objects.create(
            category=category,
            name="Referral laptop",
            slug="referral-laptop",
            price=Decimal("1000000.00"),
            stock_quantity=2,
            is_published=True,
        )
        self.client.get(reverse("growth_ambassador_referral", args=[ambassador.code]))
        self.client.post(reverse("cart_add", kwargs={"product_id": product.pk}), {"quantity": 1})
        saved = SavedCart.objects.create(
            session_key=self.client.session.session_key,
            email="referral-buyer@example.com",
            cart_data={f"p:{product.pk}": 1},
            subtotal=product.price,
        )
        self.client.get(reverse("checkout"))
        token = self.client.session["checkout_submit_token"]

        self.client.post(
            reverse("checkout"),
            {
                "name": "Referral buyer",
                "email": "referral-buyer@example.com",
                "phone": "0700000000",
                "company_name": "",
                "billing_address": "Kampala",
                "shipping_address": "",
                "customer_note": "",
                "fulfillment_type": Order.FULFILLMENT_PICKUP,
                "checkout_token": token,
            },
        )

        order = Order.objects.get()
        saved.refresh_from_db()
        ambassador.refresh_from_db()
        conversion = AmbassadorConversion.objects.get(order=order)
        self.assertEqual(order.marketing_source, f"ambassador:{ambassador.code}")
        self.assertEqual(order.marketing_medium, "referral")
        self.assertEqual(saved.status, SavedCart.STATUS_RECOVERED)
        self.assertEqual(saved.recovered_order, order)
        self.assertEqual(conversion.ambassador, ambassador)
        self.assertEqual(ambassador.order_count, 1)
        self.assertNotIn(AMBASSADOR_SESSION_KEY, self.client.session)
