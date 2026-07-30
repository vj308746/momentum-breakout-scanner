from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from decision_engine import add_trade_decisions
from ltp_overlay import apply_stock_ltp_overlay


def decision_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Current Price": 100.10,
        "Suggested Entry": 100.00,
        "Suggested Stop Loss": 95.00,
        "Stop Loss %": 5.0,
        "Trade Quality Score": 95.0,
        "RS Score": 95.0,
        "Sector RS Score": 95.0,
        "VCP Score": 95.0,
        "Volume Score": 95.0,
        "EMA Bullish Alignment": True,
        "20D Avg Volume": 1_000_000,
        "Current Volume": 2_000_000,
        "Upper Circuit": 100.20,
        "Lower Circuit": 82.00,
        "Circuit Data Available": True,
    }
    row.update(overrides)
    return row


class CircuitGuardTests(unittest.TestCase):
    def test_buy_now_is_downgraded_near_upper_circuit(self) -> None:
        report = pd.DataFrame([decision_row()])

        with patch(
            "decision_engine.LIVE_BUY_REQUIRES_VOLUME",
            False,
        ):
            result = add_trade_decisions(
                report,
                {
                    "Market Status": "BULLISH",
                    "Market Bullish": True,
                },
            )

        self.assertEqual(result.loc[0, "Action"], "WATCH")
        self.assertEqual(
            result.loc[0, "Circuit Execution Status"],
            "UPPER CIRCUIT BLOCK",
        )
        self.assertFalse(
            bool(result.loc[0, "Show Active Trade Plan"])
        )

    def test_clear_circuit_allows_buy_now(self) -> None:
        report = pd.DataFrame(
            [
                decision_row(
                    **{
                        "Upper Circuit": 120.00,
                        "Lower Circuit": 80.00,
                    }
                )
            ]
        )

        with patch(
            "decision_engine.LIVE_BUY_REQUIRES_VOLUME",
            False,
        ):
            result = add_trade_decisions(
                report,
                {
                    "Market Status": "BULLISH",
                    "Market Bullish": True,
                },
            )

        self.assertEqual(result.loc[0, "Action"], "BUY NOW")
        self.assertEqual(
            result.loc[0, "Circuit Execution Status"],
            "CLEAR",
        )

    def test_entry_above_upper_circuit_is_not_near_trigger(self) -> None:
        report = pd.DataFrame(
            [
                decision_row(
                    **{
                        "Current Price": 99.0,
                        "Suggested Entry": 101.0,
                        "Upper Circuit": 100.0,
                    }
                )
            ]
        )

        result = add_trade_decisions(
            report,
            {
                "Market Status": "BULLISH",
                "Market Bullish": True,
            },
        )

        self.assertEqual(result.loc[0, "Action"], "WATCH")
        self.assertEqual(
            result.loc[0, "Circuit Execution Status"],
            "ENTRY UNREACHABLE TODAY",
        )

    def test_overlay_surfaces_full_quote_circuit_fields(self) -> None:
        result = {
            "Current Price": 98.0,
            "52W High": 110.0,
            "52W Low": 70.0,
            "50 DMA": 90.0,
            "150 DMA": 85.0,
            "200 DMA": 80.0,
            "50 DMA > 150 DMA": True,
            "150 DMA > 200 DMA": True,
            "200 DMA Rising": True,
            "Pivot Price": 100.0,
            "Suggested Entry": 100.1,
            "20D Avg Volume": 1_000_000,
        }
        quote = {
            "last_price": 99.5,
            "cp": 98.0,
            "volume": 500_000,
            "upper_circuit_limit": 100.0,
            "lower_circuit_limit": 80.0,
            "total_sell_quantity": 0,
            "total_buy_quantity": 250_000,
        }

        updated = apply_stock_ltp_overlay(
            result,
            quote,
        )

        self.assertTrue(updated["Circuit Data Available"])
        self.assertEqual(updated["Upper Circuit"], 100.0)
        self.assertEqual(updated["Lower Circuit"], 80.0)
        self.assertEqual(updated["Total Sell Quantity"], 0.0)


if __name__ == "__main__":
    unittest.main()
