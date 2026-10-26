"""Тесты расчёта комиссии и форматирования. Запуск: python -m unittest discover -s tests"""
from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.rates import (  # noqa: E402
    LimitError,
    apply_fee,
    check_limits,
    format_ton,
    format_usd,
    to_ton,
    to_usd,
)


class ApplyFeeTest(unittest.TestCase):
    def test_one_percent(self):
        quote = apply_fee("100", 1.0)
        self.assertEqual(quote.fee, Decimal("1.000000000"))
        self.assertEqual(quote.net, Decimal("99.000000000"))

    def test_zero_fee(self):
        quote = apply_fee("2.5", 0)
        self.assertEqual(quote.fee, Decimal("0.000000000"))
        self.assertEqual(quote.net, Decimal("2.500000000"))

    def test_fractional_amount(self):
        quote = apply_fee("0.123456789", 1.5)
        self.assertEqual(quote.gross, Decimal("0.123456789"))
        self.assertLess(quote.net, quote.gross)
        self.assertEqual(quote.net + quote.fee, quote.gross)

    def test_rejects_non_positive(self):
        with self.assertRaises(ValueError):
            apply_fee("0", 1)
        with self.assertRaises(ValueError):
            apply_fee("-1", 1)

    def test_rejects_fee_out_of_range(self):
        with self.assertRaises(ValueError):
            apply_fee("1", -1)
        with self.assertRaises(ValueError):
            apply_fee("1", 101)

    def test_net_never_exceeds_total(self):
        for amount in ("0.000000001", "1", "12345.6789"):
            for fee in (0, 0.5, 1, 7.5, 100):
                quote = apply_fee(amount, fee)
                self.assertEqual(quote.net + quote.fee, quote.gross, msg=f"{amount} @ {fee}%")


class ConvertTest(unittest.TestCase):
    def test_to_usd(self):
        self.assertEqual(to_usd("2", "5.25"), Decimal("10.50"))

    def test_to_ton(self):
        self.assertEqual(to_ton("5.25", "5.25"), Decimal("1.0000"))

    def test_to_ton_rejects_bad_rate(self):
        with self.assertRaises(ValueError):
            to_ton("1", "0")

    def test_format_ton_trims_zeros(self):
        self.assertEqual(format_ton("1234.5000", 4), "1 234.5")
        self.assertEqual(format_ton("0.1000", 4), "0.1")
        self.assertEqual(format_ton("1000000", 2), "1 000 000")

    def test_format_usd(self):
        self.assertEqual(format_usd("1234.5"), "1 234.50 $")


class LimitsTest(unittest.TestCase):
    def test_inside_range(self):
        self.assertEqual(check_limits("5", "1", "10"), Decimal("5"))

    def test_edges_inclusive(self):
        self.assertEqual(check_limits("1", "1", "10"), Decimal("1"))
        self.assertEqual(check_limits("10", "1", "10"), Decimal("10"))

    def test_below_min(self):
        with self.assertRaises(LimitError) as ctx:
            check_limits("0.99", "1", "10")
        self.assertIn("Минимальная", str(ctx.exception))

    def test_above_max(self):
        with self.assertRaises(LimitError) as ctx:
            check_limits("10.01", "1", "10")
        self.assertIn("Максимальная", str(ctx.exception))

    def test_non_positive(self):
        with self.assertRaises(LimitError):
            check_limits("0", "1", "10")


if __name__ == "__main__":
    unittest.main()
