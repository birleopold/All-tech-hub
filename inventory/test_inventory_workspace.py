from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product


class InventoryWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("inventory-staff", password="pw", is_staff=True)
        category = Category.objects.create(name="Workspace Stock", slug="workspace-stock")
        Product.objects.create(
            category=category,
            kind=Product.KIND_PHYSICAL,
            name="Tracked laptop",
            slug="tracked-laptop",
            price=Decimal("1500000"),
            track_inventory=True,
            stock_quantity=1,
            reorder_level=2,
            is_published=True,
        )
        Product.objects.create(
            category=category,
            kind=Product.KIND_SERVICE,
            name="Installation service",
            slug="installation-service",
            price=Decimal("50000"),
            track_inventory=False,
            is_published=True,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_inventory_workspace_renders_physical_product_metrics(self):
        response = self.client.get(reverse("staff_inventory"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["inventory_stats"]["products"], 1)
        self.assertEqual(response.context["inventory_stats"]["published"], 1)
        self.assertEqual(response.context["inventory_stats"]["tracked"], 1)
        self.assertEqual(response.context["inventory_stats"]["low_stock"], 1)
        self.assertContains(response, "Inventory overview")
        self.assertContains(response, "Quick stock adjustment")
        self.assertContains(response, "staff-summary-grid--five")
        self.assertContains(response, "1 item at or below reorder level")
