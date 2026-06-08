from django.test import TestCase

from crm.models import Customer, CustomerAddress


class CustomerAddressTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Pat", email="pat@example.com")

    def test_setting_default_unsets_other_defaults(self):
        a1 = CustomerAddress.objects.create(
            customer=self.customer,
            label="Home",
            line1="1 First",
            city="Kampala",
            is_default=True,
        )
        a2 = CustomerAddress.objects.create(
            customer=self.customer,
            label="Office",
            line1="2 Second",
            city="Kampala",
            is_default=True,
        )
        a1.refresh_from_db()
        self.assertFalse(a1.is_default)
        self.assertTrue(a2.is_default)

    def test_as_text_includes_full_address(self):
        addr = CustomerAddress.objects.create(
            customer=self.customer,
            label="Home",
            line1="Plot 1",
            line2="Suite 4",
            city="Kampala",
            region="Central",
            postal_code="256",
            country="Uganda",
        )
        text = addr.as_text()
        self.assertIn("Plot 1", text)
        self.assertIn("Suite 4", text)
        self.assertIn("Kampala", text)
        self.assertIn("Uganda", text)

    def test_kind_default_is_both(self):
        addr = CustomerAddress.objects.create(
            customer=self.customer, label="Default", line1="Z", city="K"
        )
        self.assertEqual(addr.kind, CustomerAddress.KIND_BOTH)
