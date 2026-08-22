from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from commerce.models import Order
from crm.models import Customer
from growth.models import Ambassador, AmbassadorConversion
from growth.services import approve_ambassador_conversion, pay_ambassador_conversion


class AmbassadorPayoutTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(username="ambassador-finance", is_staff=True)
        customer = Customer.objects.create(name="Referral customer", email="referred@example.com")
        order = Order.objects.create(reference="ORD-AMB-001", customer=customer, contact_name=customer.name, contact_email=customer.email, total=Decimal("1000000.00"))
        ambassador = Ambassador.objects.create(name="Referral partner", code="partner")
        self.conversion = AmbassadorConversion.objects.create(ambassador=ambassador, order=order, revenue=order.total, commission_amount=Decimal("50000.00"))

    def test_approval_and_payment_have_separate_audited_steps(self):
        approved = approve_ambassador_conversion(self.conversion, actor=self.actor)
        self.assertEqual(approved.status, AmbassadorConversion.STATUS_APPROVED)
        self.assertEqual(approved.approved_by, self.actor)
        paid = pay_ambassador_conversion(approved, actor=self.actor, payout_reference="MTN-123456")
        self.assertEqual(paid.status, AmbassadorConversion.STATUS_PAID)
        self.assertEqual(paid.payout_reference, "MTN-123456")
        self.assertEqual(paid.paid_by, self.actor)

    def test_payment_requires_approval_and_reference(self):
        with self.assertRaises(ValidationError):
            pay_ambassador_conversion(self.conversion, actor=self.actor, payout_reference="MTN-123456")
        approved = approve_ambassador_conversion(self.conversion, actor=self.actor)
        with self.assertRaises(ValidationError):
            pay_ambassador_conversion(approved, actor=self.actor, payout_reference="")

    def test_cancelled_order_cannot_be_approved(self):
        self.conversion.order.status = Order.STATUS_CANCELLED
        self.conversion.order.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            approve_ambassador_conversion(self.conversion, actor=self.actor)
