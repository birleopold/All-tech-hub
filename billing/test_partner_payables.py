from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from billing.models import CommercialDocument, CommercialLine, allocate_document_number
from billing.partner_payables import partner_payables_summary


class PartnerPayablesTests(TestCase):
    def _document(self):
        return CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_RECEIPT,
            number=allocate_document_number("REC"),
            customer_name="Walk-in customer",
            status=CommercialDocument.STATUS_ISSUED,
            issue_date=timezone.localdate(),
            tax_rate=Decimal("0"),
        )

    def test_summary_groups_external_items_and_subcontracted_services(self):
        document = self._document()
        neighbor_line = CommercialLine.objects.create(
            document=document,
            description="External laptop",
            source_type=CommercialLine.SOURCE_EXTERNAL,
            supplier_name="Neighbor shop",
            quantity=Decimal("1"),
            unit_price=Decimal("1300000"),
            unit_cost=Decimal("1000000"),
        )
        service_line = CommercialLine.objects.create(
            document=document,
            description="Subcontracted installation",
            source_type=CommercialLine.SOURCE_SERVICE,
            supplier_name="Field technician",
            quantity=Decimal("1"),
            unit_price=Decimal("500000"),
            unit_cost=Decimal("350000"),
        )
        own_line = CommercialLine.objects.create(
            document=document,
            description="Own cable",
            source_type=CommercialLine.SOURCE_STOCK,
            quantity=Decimal("1"),
            unit_price=Decimal("20000"),
            unit_cost=Decimal("10000"),
        )
        document.recalculate_from_lines()
        document.save()

        rows = partner_payables_summary([neighbor_line, service_line, own_line])

        self.assertEqual(len(rows), 2)
        amount_due_by_partner = {row["partner"]: row["amount_due"] for row in rows}
        self.assertEqual(amount_due_by_partner["Neighbor shop"], Decimal("1000000.00"))
        self.assertEqual(amount_due_by_partner["Field technician"], Decimal("350000.00"))
