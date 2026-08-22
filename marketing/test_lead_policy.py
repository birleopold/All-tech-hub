import unittest

from marketing.lead_policy import classify_enquiry, response_minutes, uganda_whatsapp_digits


class LeadPolicyTests(unittest.TestCase):
    def test_quotes_and_support_receive_higher_priority(self):
        self.assertEqual(classify_enquiry("quote"), ("quote", "high"))
        self.assertEqual(classify_enquiry("support"), ("support", "high"))
        self.assertEqual(classify_enquiry("product"), ("product", "normal"))

    def test_unknown_request_type_is_safely_normalized(self):
        self.assertEqual(classify_enquiry("unexpected"), ("other", "normal"))

    def test_priority_changes_response_deadline(self):
        self.assertEqual(response_minutes("urgent", 30), 5)
        self.assertEqual(response_minutes("high", 30), 15)
        self.assertEqual(response_minutes("normal", 30), 30)
        self.assertEqual(response_minutes("low", 30), 60)

    def test_uganda_whatsapp_numbers_are_normalized(self):
        self.assertEqual(uganda_whatsapp_digits("0700 123 456"), "256700123456")
        self.assertEqual(uganda_whatsapp_digits("+256 700 123 456"), "256700123456")
        self.assertEqual(uganda_whatsapp_digits("123"), "")


if __name__ == "__main__":
    unittest.main()
