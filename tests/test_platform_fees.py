import unittest
from decimal import Decimal

from app.services import platform_fees


class PlatformFeeTests(unittest.TestCase):
    def setUp(self) -> None:
        platform_fees.reset_platform_profit_total()

    def test_calculates_platform_fee_from_trade_value(self) -> None:
        fee = platform_fees.calculate_platform_fee(50, "130.10", Decimal("0.001"))

        self.assertEqual(fee, Decimal("6.51"))

    def test_non_positive_trade_inputs_return_zero_fee(self) -> None:
        self.assertEqual(
            platform_fees.calculate_platform_fee(0, "130.10", Decimal("0.001")),
            Decimal("0.00"),
        )
        self.assertEqual(
            platform_fees.calculate_platform_fee(50, 0, Decimal("0.001")),
            Decimal("0.00"),
        )

    def test_records_platform_profit(self) -> None:
        platform_fees.record_platform_profit("6.51")
        platform_fees.record_platform_profit("1.234")

        self.assertEqual(platform_fees.get_platform_profit_total(), Decimal("7.74"))


if __name__ == "__main__":
    unittest.main()
