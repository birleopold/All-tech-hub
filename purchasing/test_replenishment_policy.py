import unittest

from purchasing.replenishment import suggested_reorder_quantity


class ReplenishmentPolicyTests(unittest.TestCase):
    def test_restores_reorder_buffer(self):
        self.assertEqual(suggested_reorder_quantity(on_hand=2, reorder_level=5, recent_sales=0, recent_enquiries=0, pending_inbound=0), 8)

    def test_accounts_for_actual_demand(self):
        self.assertEqual(suggested_reorder_quantity(on_hand=2, reorder_level=3, recent_sales=12, recent_enquiries=4, pending_inbound=0), 13)

    def test_does_not_duplicate_incoming_stock(self):
        self.assertEqual(suggested_reorder_quantity(on_hand=2, reorder_level=5, recent_sales=0, recent_enquiries=0, pending_inbound=8), 0)

    def test_handles_empty_or_negative_inputs(self):
        self.assertEqual(suggested_reorder_quantity(on_hand=-3, reorder_level=0, recent_sales=None, recent_enquiries=4, pending_inbound=-2), 4)


if __name__ == "__main__":
    unittest.main()
