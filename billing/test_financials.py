from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from billing.financials import (
    document_business_cost,
    document_owner_payout,
    document_profit,
    document_recognized_income,
    line_business_cost,
    line_owner_payout,
    line_profit,
    line_recognized_income,
    queryset_financial_summary,
)
from billing.models import CommercialDocument, CommercialLine, allocate_document_number


class CommissionAwareFinancialTests(TestCase):
    def _document(self):
        return CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_RECEIPT,
            number=allocate_document_number("REC"),
            customer_name="Walk-in customer",
            status=CommercialDocument.STATUS_ISSUED,
            issue_date=timezone.localdate(),
            tax_rate=Decimal("0"),
        )

    def test_neighbor_item_recognizes_only_markup_as_income(self):
        document = self._document()
        line = CommercialLine.objects.create(
            document=document,
            description="Neighbor laptop",
            source_type=CommercialLine.SOURCE_EXTERNAL,
            supplier_name="Neighbor shop",
            quantity=Decimal("1"),
            unit_price=Decimal("1300000"),
            unit_cost=Decimal("1000000"),
        )
        document.recalculate_from_lines()
        document.save()

        self.assertEqual(line_recognized_income(line), Decimal("300000.00"))
        self.assertEqual(line_owner_payout(line), Decimal("1000000.00"))
        self.assertEqual(line_business_cost(line), Decimal("0.00"))
        self.assertEqual(line_profit(line), Decimal("300000.00"))
        self.assertEqual(document_recognized_income(document), Decimal("300000.00"))
        self.assertEqual(document_owner_payout(document), Decimal("1000000.00"))
        self.assertEqual(document_business_cost(document), Decimal("0.00"))
        self.assertEqual(document_profit(document), Decimal("300000.00"))

    def test_own_stock_keeps_normal_revenue_and_cost(self):
        document = self._document()
        line = CommercialLine.objects.create(
            document=document,
            description="Own stock mouse",
            source_type=CommercialLine.SOURCE_STOCK,
            quantity=Decimal("1"),
            unit_price=Decimal("50000"),
            unit_cost=Decimal("30000"),
        )
        document.recalculate_from_lines()
        document.save()

        self.assertEqual(line_recognized_income(line), Decimal("50000.00"))
        self.assertEqual(line_owner_payout(line), Decimal("0.00"))
        self.assertEqual(line_business_cost(line), Decimal("30000.00"))
        self.assertEqual(line_profit(line), Decimal("20000.00"))

    def test_financial_summary_separates_customer_total_from_income(self):
        document = self._document()
        CommercialLine.objects.create(
            document=document,
            description="Neighbor monitor",
            source_type=CommercialLine.SOURCE_CONSIGNMENT,
            supplier_name="Neighbor shop",
            quantity=Decimal("1"),
            unit_price=Decimal("800000"),
            unit_cost=Decimal("700000"),
        )
        CommercialLine.objects.create(
            document=document,
            description="Installation service",
            source_type=CommercialLine.SOURCE_SERVICE,
            quantity=Decimal("1"),
            unit_price=Decimal("50000"),
            unit_cost=Decimal("0"),
        )
        document.recalculate_from_lines()
        document.save()

        summary = queryset_financial_summary([document])

        self.assertEqual(summary["customer_total"], Decimal("850000.00"))
        self.assertEqual(summary["recognized_income"], Decimal("150000.00"))
        self.assertEqual(summary["owner_payout"], Decimal("700000.00"))
        self.assertEqual(summary["business_cost"], Decimal("0.00"))
        self.assertEqual(summary["profit"], Decimal("150000.00"))
