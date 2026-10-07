import json
from pathlib import Path
import random
import unittest

from business_metrics import ContractError, Order, Refund, summarize


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class ContractTests(unittest.TestCase):
    def test_decision_table(self):
        cases = json.loads((FIXTURES / "decision-table.json").read_text())
        for case in cases:
            with self.subTest(case=case["id"]):
                order = Order(**case["order"])
                result = summarize([order], [], "2026-07", complete_sources=True)
                self.assertEqual(bool(result.paid_order_ids), case["paid_in_month"])
                self.assertEqual(bool(result.shipped_order_ids), case["shipped_in_month"])

    def test_sample_totals_and_populations(self):
        data = json.loads((FIXTURES / "synthetic-orders.json").read_text())
        result = summarize([Order(**x) for x in data["orders"]],
                           [Refund(**x) for x in data["refunds"]],
                           "2026-07", complete_sources=True).to_dict()
        self.assertEqual(result["paid_order_ids"], ["A", "B", "D", "E", "F"])
        self.assertEqual(result["shipped_order_ids"], ["A", "C"])
        self.assertEqual(result["refund_ids"], ["R1"])
        self.assertEqual(result["paid_gross"], "260.00")
        self.assertEqual(result["shipped_gross"], "180.00")
        self.assertEqual(result["refunds"], "20.00")
        self.assertEqual(result["cash_net"], "240.00")

    def test_later_refund_preserves_original_cash_in(self):
        order = Order("A", "100.00", "EUR", "2026-07-05T10:00:00Z")
        refund = Refund("R", "A", "100.00", "2026-08-05T10:00:00Z")
        july = summarize([order], [refund], "2026-07", complete_sources=True)
        august = summarize([order], [refund], "2026-08", complete_sources=True)
        self.assertEqual(str(july.cash_net), "100.00")
        self.assertEqual(str(august.cash_net), "-100.00")

    def test_duplicates_block_publication(self):
        order = Order("A", "10.00", "EUR", "2026-07-01T00:00:00Z")
        with self.assertRaises(ContractError):
            summarize([order, order], [], "2026-07", complete_sources=True)
        refund = Refund("R", "A", "1.00", "2026-07-02T00:00:00Z")
        with self.assertRaises(ContractError):
            summarize([order], [refund, refund], "2026-07", complete_sources=True)

    def test_partial_refunds_are_checked_cumulatively(self):
        order = Order("A", "10.00", "EUR", "2026-06-01T00:00:00Z")
        refunds = [Refund("R1", "A", "6.00", "2026-06-02T00:00:00Z"),
                   Refund("R2", "A", "5.00", "2026-07-02T00:00:00Z")]
        with self.assertRaises(ContractError):
            summarize([order], refunds, "2026-07", complete_sources=True)

    def test_unknown_reference_blocks_publication(self):
        with self.assertRaises(ContractError):
            summarize([], [Refund("R", "unknown", "2.00", "2026-07-02T00:00:00Z")],
                      "2026-07", complete_sources=True)

    def test_incomplete_sources_do_not_become_zero(self):
        for flag in [False, None, "true", 1]:
            with self.subTest(flag=flag), self.assertRaises(ContractError):
                summarize([], [], "2026-07", complete_sources=flag)

    def test_complete_empty_month_is_a_known_zero(self):
        result = summarize([], [], "2026-07", complete_sources=True)
        self.assertEqual(result.to_dict()["paid_gross"], "0.00")

    def test_invalid_money_currency_and_events(self):
        invalid = [
            Order("A", "NaN", "EUR", "2026-07-01T00:00:00Z"),
            Order("A", "-1", "EUR", "2026-07-01T00:00:00Z"),
            Order("A", "0.001", "EUR", "2026-07-01T00:00:00Z"),
            Order("A", 1.1, "EUR", "2026-07-01T00:00:00Z"),
            Order("A", "10", "USD", "2026-07-01T00:00:00Z"),
            Order("A", "10", "EUR", "2026-07-01T00:00:00"),
            Order("A", "10", "EUR", None),
            Order("A", "10", "EUR", "2026-07-02T00:00:00Z", "2026-07-01T00:00:00Z"),
            Order("", "10", "EUR", "2026-07-01T00:00:00Z"),
        ]
        for order in invalid:
            with self.subTest(order=order), self.assertRaises(ContractError):
                summarize([order], [], "2026-07", complete_sources=True)

    def test_refund_before_payment_is_rejected(self):
        with self.assertRaises(ContractError):
            summarize([Order("A", "10", "EUR", "2026-07-05T00:00:00Z")],
                      [Refund("R", "A", "1", "2026-07-04T00:00:00Z")],
                      "2026-07", complete_sources=True)

    def test_invalid_months(self):
        for month in ["2026-13", "2026-00", "2026-7", "0000-01", "2026-07-extra", None]:
            with self.subTest(month=month), self.assertRaises(ContractError):
                summarize([], [], month, complete_sources=True)

    def test_unknown_timezone(self):
        with self.assertRaises(ContractError):
            summarize([], [], "2026-07", complete_sources=True, timezone_name="Unknown/City")

    def test_order_and_refund_permutations_do_not_change_result(self):
        data = json.loads((FIXTURES / "synthetic-orders.json").read_text())
        orders = [Order(**x) for x in data["orders"]]
        refunds = [Refund(**x) for x in data["refunds"]]
        expected = summarize(orders, refunds, "2026-07", complete_sources=True)
        rng = random.Random(77)
        for _ in range(30):
            rng.shuffle(orders);rng.shuffle(refunds)
            self.assertEqual(summarize(orders, refunds, "2026-07", complete_sources=True), expected)

    def test_monthly_partition_reconciles_all_supplied_cash_events(self):
        data = json.loads((FIXTURES / "synthetic-orders.json").read_text())
        orders = [Order(**x) for x in data["orders"]]
        refunds = [Refund(**x) for x in data["refunds"]]
        results = [summarize(orders, refunds, month, complete_sources=True)
                   for month in ["2026-06", "2026-07", "2026-08"]]
        self.assertEqual(sum(x.paid_gross for x in results), 330)
        self.assertEqual(sum(x.refunds for x in results), 30)
        self.assertEqual(sum(x.cash_net for x in results), 300)


if __name__ == "__main__":
    unittest.main()
