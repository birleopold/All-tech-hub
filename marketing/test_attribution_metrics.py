import unittest
from decimal import Decimal

from marketing.attribution_metrics import merge_channel_metrics, percentage


class MarketingAttributionMetricTests(unittest.TestCase):
    def test_merges_clicks_leads_orders_and_revenue(self):
        rows = merge_channel_metrics(
            [{"source": "tiktok", "medium": "social", "clicks": 40}],
            [{"source": "tiktok", "medium": "social", "leads": 8}],
            [
                {
                    "source": "tiktok",
                    "medium": "social",
                    "orders": 2,
                    "revenue": Decimal("1500000.00"),
                }
            ],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["click_to_lead_rate"], Decimal("20.00"))
        self.assertEqual(rows[0]["click_to_order_rate"], Decimal("5.00"))
        self.assertEqual(rows[0]["average_order_value"], Decimal("750000.00"))

    def test_no_clicks_never_fabricates_conversion_rate(self):
        rows = merge_channel_metrics(
            [],
            [],
            [{"source": "whatsapp", "medium": "chat", "orders": 1, "revenue": "50000"}],
        )

        self.assertEqual(rows[0]["click_to_order_rate"], Decimal("0.00"))
        self.assertEqual(percentage(4, 0), Decimal("0.00"))

    def test_highest_realized_revenue_is_ranked_first(self):
        rows = merge_channel_metrics(
            [
                {"source": "facebook", "medium": "social", "clicks": 300},
                {"source": "instagram", "medium": "social", "clicks": 20},
            ],
            [],
            [
                {"source": "facebook", "medium": "social", "orders": 1, "revenue": "50"},
                {"source": "instagram", "medium": "social", "orders": 2, "revenue": "200"},
            ],
        )

        self.assertEqual([row["source"] for row in rows], ["instagram", "facebook"])


if __name__ == "__main__":
    unittest.main()
