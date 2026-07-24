from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from billing.models import CommercialDocument
from catalog.models import Category, Product
from commerce.models import Order
from core.models import CompanySettings, ContactMessage, StaffNotification, SupportTicket
from crm.models import Customer
from inventory.models import StockTake
from messaging.models import OutboundEmail
from operations.models import JobCard
from purchasing.models import PurchaseOrder, Supplier


class StaffWorkspaceCompletionTests(TestCase):
    """Smoke-test every major redesigned staff surface and its shared shell."""

    @classmethod
    def setUpTestData(cls):
        CompanySettings.load()
        cls.user = get_user_model().objects.create_user(
            username="workspace-admin",
            password="pw",
            is_staff=True,
            is_superuser=True,
        )
        cls.customer = Customer.objects.create(
            name="Workspace Customer",
            company_name="Workspace Ltd",
            email="customer@example.com",
            phone="0700000000",
        )
        cls.category = Category.objects.create(name="Laptops", slug="laptops")
        cls.product = Product.objects.create(
            category=cls.category,
            kind=Product.KIND_PHYSICAL,
            name="Workspace Laptop",
            slug="workspace-laptop",
            sku="WS-LAP-1",
            price=Decimal("2500000.00"),
            stock_quantity=4,
            reorder_level=1,
        )
        cls.order = Order.objects.create(
            reference="ORD-WORKSPACE-1",
            customer=cls.customer,
            contact_name=cls.customer.name,
            contact_email=cls.customer.email,
            contact_phone=cls.customer.phone,
            subtotal=Decimal("2500000.00"),
            total=Decimal("2500000.00"),
        )
        cls.order.lines.create(
            product=cls.product,
            description=cls.product.name,
            sku=cls.product.sku,
            quantity=1,
            unit_price=cls.product.price,
        )
        cls.document = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number="INV-WORKSPACE-1",
            customer=cls.customer,
            customer_name=cls.customer.name,
            customer_email=cls.customer.email,
            customer_phone=cls.customer.phone,
            title="Workspace invoice",
            subtotal=Decimal("2500000.00"),
            total=Decimal("2500000.00"),
            created_by=cls.user,
        )
        cls.job = JobCard.objects.create(
            customer=cls.customer,
            title="Workspace repair",
            device_type="Laptop",
            device_make="Demo",
            device_model="Model 1",
            serial_number="SERIAL-WORKSPACE-1",
            problem_reported="Does not power on",
            assigned_to=cls.user,
        )
        cls.ticket = SupportTicket.objects.create(
            customer=cls.customer,
            created_by=cls.user,
            subject="Workspace support request",
            description="Please review this device.",
            assigned_to=cls.user,
        )
        cls.supplier = Supplier.objects.create(
            name="Workspace Supplier",
            email="supplier@example.com",
        )
        cls.purchase_order = PurchaseOrder.objects.create(
            supplier=cls.supplier,
            created_by=cls.user,
        )
        cls.stocktake = StockTake.objects.create(
            name="Workspace cycle count",
            created_by=cls.user,
        )
        cls.email = OutboundEmail.objects.create(
            to_email=cls.customer.email,
            normalized_to_email=cls.customer.email,
            category=OutboundEmail.CATEGORY_TRANSACTIONAL,
            subject="Workspace delivery evidence",
            body="Hello from the workspace.",
            status=OutboundEmail.STATUS_DELIVERED,
            created_by=cls.user,
        )
        ContactMessage.objects.create(
            name="Website Visitor",
            email="visitor@example.com",
            subject="Website enquiry",
            message="I need help choosing a laptop.",
        )
        StaffNotification.objects.create(
            recipient=cls.user,
            message="Workspace notification",
            link=reverse("staff_job_detail", args=[cls.job.pk]),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_all_primary_staff_routes_render(self):
        route_names = [
            "staff_dashboard",
            "staff_orders",
            "staff_documents",
            "staff_inventory",
            "staff_products",
            "staff_stock_movements",
            "staff_stocktakes",
            "staff_purchasing",
            "staff_warranty_center",
            "staff_job_bench",
            "staff_jobs",
            "staff_job_calendar",
            "staff_tickets",
            "staff_contact_messages",
            "staff_notifications",
            "staff_search",
            "staff_reports",
            "staff_audit_log",
            "staff_security_diagnostics",
            "staff_business_hours",
            "staff_email_log",
        ]
        for route_name in route_names:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "staff-app")
                self.assertContains(response, "staff_workspace_final_polish.css")

    def test_all_redesigned_detail_pages_render(self):
        urls = [
            reverse("staff_order_detail", args=[self.order.pk]),
            reverse("staff_document_view", args=[self.document.pk]),
            reverse("staff_job_detail", args=[self.job.pk]),
            reverse("staff_ticket_detail", args=[self.ticket.pk]),
            reverse("staff_product_edit", args=[self.product.pk]),
            reverse("staff_po_edit", args=[self.purchase_order.pk]),
            reverse("staff_stocktake_detail", args=[self.stocktake.pk]),
            reverse("staff_email_log_detail", args=[self.email.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "staff-detail-header")

    def test_navigation_covers_specialist_tools(self):
        response = self.client.get(reverse("staff_dashboard"))
        self.assertContains(response, "Stock movement ledger")
        self.assertContains(response, "New support ticket")
        self.assertContains(response, "Email activity log")

    def test_queue_metrics_render_real_counts(self):
        ticket_response = self.client.get(reverse("staff_tickets"))
        self.assertContains(ticket_response, "Support queue")
        self.assertContains(ticket_response, self.ticket.reference)

        contact_response = self.client.get(reverse("staff_contact_messages"))
        self.assertContains(contact_response, "Needs attention")
        self.assertContains(contact_response, "Website enquiry")

        notification_response = self.client.get(reverse("staff_notifications"))
        self.assertContains(notification_response, "Workspace notification")
