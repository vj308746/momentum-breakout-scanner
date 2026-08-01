from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from breakout_engine import finalise_breakout_report
from liquidity import add_liquidity_gate


class LiquidityGateTests(unittest.TestCase):
    def test_liquid_stock_passes(self) -> None:
        report = pd.DataFrame(
            [
                {
                    "Current Price": 200.0,
                    "20D Avg Volume": 200_000.0,
                }
            ]
        )
        with (
            patch("liquidity.MIN_PRICE", 50.0),
            patch(
                "liquidity.MIN_AVG_TURNOVER_VALUE",
                20_000_000.0,
            ),
        ):
            result = add_liquidity_gate(report)

        self.assertTrue(
            bool(result.loc[0, "Liquidity Eligible"])
        )
        self.assertEqual(
            result.loc[0, "20D Avg Turnover Value"],
            40_000_000.0,
        )

    def test_low_price_is_excluded(self) -> None:
        report = pd.DataFrame(
            [
                {
                    "Current Price": 25.0,
                    "20D Avg Volume": 2_000_000.0,
                }
            ]
        )
        with (
            patch("liquidity.MIN_PRICE", 50.0),
            patch(
                "liquidity.MIN_AVG_TURNOVER_VALUE",
                20_000_000.0,
            ),
        ):
            result = add_liquidity_gate(report)

        self.assertFalse(
            bool(result.loc[0, "Liquidity Eligible"])
        )
        self.assertEqual(
            result.loc[0, "Liquidity Status"],
            "FAIL - PRICE",
        )

    def test_thin_turnover_is_excluded(self) -> None:
        report = pd.DataFrame(
            [
                {
                    "Current Price": 100.0,
                    "20D Avg Volume": 100_000.0,
                }
            ]
        )
        with (
            patch("liquidity.MIN_PRICE", 50.0),
            patch(
                "liquidity.MIN_AVG_TURNOVER_VALUE",
                20_000_000.0,
            ),
        ):
            result = add_liquidity_gate(report)

        self.assertFalse(
            bool(result.loc[0, "Liquidity Eligible"])
        )
        self.assertEqual(
            result.loc[0, "Liquidity Status"],
            "FAIL - TURNOVER",
        )

    def test_liquidity_failure_blocks_breakout_eligibility(
        self,
    ) -> None:
        report = pd.DataFrame(
            [
                {
                    "Any Pattern Match": True,
                    "Movement Scanner Eligible": True,
                    "RS Score": 95,
                    "Liquidity Eligible": False,
                    "Matched Patterns": "Flat Base",
                }
            ]
        )
        result = finalise_breakout_report(report)
        self.assertFalse(
            bool(result.loc[0, "Breakout Scanner Eligible"])
        )


if __name__ == "__main__":
    unittest.main()
