import unittest

from marketing.readiness import evaluate_growth_phases


class GrowthPhaseReadinessTests(unittest.TestCase):
    def test_empty_business_exposes_every_commercial_phase(self):
        result = evaluate_growth_phases({})

        self.assertEqual(
            [phase["name"] for phase in result["phases"]],
            [
                "Discovery",
                "Trust",
                "Acquisition",
                "Conversion",
                "Fulfillment",
                "Retention",
                "Advocacy",
            ],
        )
        self.assertEqual(result["total_checks"], 21)
        self.assertGreater(len(result["priority_actions"]), 0)
        self.assertLess(result["coverage_score"], 100)

    def test_complete_business_marks_all_phases_ready(self):
        result = evaluate_growth_phases(
            {
                "published_count": 12,
                "connected_channels": 4,
                "analytics_ready": True,
                "missing_images": 0,
                "missing_descriptions": 0,
                "published_reviews": 8,
                "business_profile_ready": True,
                "tracked_links": 6,
                "scheduled_content": 3,
                "clicks_30d": 240,
                "leads_30d": 18,
                "overdue_follow_ups": 0,
                "orders_30d": 9,
                "unavailable_products": 0,
                "aged_open_orders": 0,
                "shipment_exceptions": 0,
                "cart_recovery_ready": True,
                "loyalty_accounts": 30,
                "repeat_customers": 7,
                "active_ambassadors": 2,
                "ambassador_conversions": 3,
            }
        )

        self.assertEqual(result["coverage_score"], 100)
        self.assertEqual(result["ready_phases"], 7)
        self.assertEqual(result["priority_actions"], [])

    def test_missing_email_blocks_cart_recovery(self):
        result = evaluate_growth_phases({"cart_recovery_ready": False})
        retention = next(phase for phase in result["phases"] if phase["name"] == "Retention")

        self.assertFalse(retention["checks"][0]["ready"])
        self.assertIn("live email", retention["checks"][0]["action"])

    def test_overdue_follow_up_becomes_actionable(self):
        result = evaluate_growth_phases({"overdue_follow_ups": 2})

        self.assertTrue(
            any(
                action["phase"] == "Conversion" and "overdue" in action["action"]
                for action in result["priority_actions"]
            )
        )


if __name__ == "__main__":
    unittest.main()
