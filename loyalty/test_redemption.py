from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from crm.models import Customer
from loyalty.models import LoyaltyAccount, LoyaltyTransaction
from loyalty.services import redeem_loyalty_points


@override_settings(LOYALTY_POINTS_ENABLED=True, LOYALTY_MIN_REDEMPTION_POINTS=50, LOYALTY_POINT_VALUE_UGX=100)
class LoyaltyRedemptionTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Reward customer", email="rewards@example.com")
        self.account = LoyaltyAccount.objects.create(customer=self.customer, points_balance=120, lifetime_points=120)
        self.actor = get_user_model().objects.create_user(username="reward-finance", is_staff=True)

    def test_redemption_creates_account_credit_and_negative_transaction(self):
        transaction_row, credit = redeem_loyalty_points(self.customer, 50, actor=self.actor)
        self.account.refresh_from_db()
        self.assertEqual(self.account.points_balance, 70)
        self.assertEqual(transaction_row.kind, LoyaltyTransaction.KIND_REDEEM)
        self.assertEqual(transaction_row.points_delta, -50)
        self.assertEqual(credit.amount, Decimal("5000.00"))
        self.assertEqual(credit.remaining_amount, Decimal("5000.00"))

    def test_insufficient_points_cannot_create_credit(self):
        with self.assertRaises(ValidationError):
            redeem_loyalty_points(self.customer, 150, actor=self.actor)
        self.assertFalse(self.customer.credits.exists())

    def test_minimum_redemption_is_enforced(self):
        with self.assertRaises(ValidationError):
            redeem_loyalty_points(self.customer, 10, actor=self.actor)
