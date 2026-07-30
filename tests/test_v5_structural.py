from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from base_stage import add_base_stage_tracking
from decision_engine import add_trade_decisions
from fundamentals import add_fundamentals_gate
from market_filter import calculate_market_status
from patterns.episodic_pivot import detect_episodic_pivot
from rs_line import calculate_rs_line_metrics


class V5StructuralTests(unittest.TestCase):
    def test_episodic_pivot_requires_gap_volume_and_breakout(self) -> None:
        close = np.full(70, 100.0)
        data = pd.DataFrame(
            {
                "Open": close.copy(),
                "High": close + 1,
                "Low": close - 1,
                "Close": close.copy(),
                "Volume": np.full(70, 1_000_000.0),
            }
        )
        data.loc[69, ["Open", "High", "Low", "Close", "Volume"]] = [
            106.0,
            110.0,
            105.0,
            109.0,
            3_000_000.0,
        ]
        result = detect_episodic_pivot(data)
        self.assertTrue(result["Episodic Pivot Match"])
        self.assertTrue(result["Episodic Pivot Mandatory Pass"])

    def test_rs_line_can_lead_price(self) -> None:
        index = pd.date_range("2025-01-01", periods=80, freq="B")
        benchmark = pd.DataFrame(
            {"Close": np.linspace(100, 80, 80)},
            index=index,
        )
        stock = pd.DataFrame(
            {"Close": np.linspace(100, 99, 80)},
            index=index,
        )
        result = calculate_rs_line_metrics(stock, benchmark)
        self.assertTrue(result["RS Line New High"])
        self.assertTrue(result["RS Line Leads Price"])

    def test_distribution_days_are_counted(self) -> None:
        close = np.linspace(100, 130, 220)
        volume = np.full(220, 1_000_000.0)
        for offset in (2, 5, 8, 11, 14):
            index = 220 - offset
            close[index] = close[index - 1] * 0.995
            volume[index] = volume[index - 1] * 1.5
        data = pd.DataFrame(
            {"Close": close, "Volume": volume}
        )
        result = calculate_market_status(data)
        self.assertGreaterEqual(result["Distribution Days"], 5)
        self.assertEqual(result["Distribution Pressure"], "ELEVATED")

    def test_distribution_uses_niftybees_volume_proxy(self) -> None:
        index = pd.date_range("2025-01-01", periods=220, freq="B")
        close = np.linspace(100, 130, 220)
        index_data = pd.DataFrame(
            {
                "Close": close,
                "Volume": np.zeros(220),
            },
            index=index,
        )
        proxy_volume = np.full(220, 1_000_000.0)
        for offset in (2, 5, 8, 11, 14):
            position = 220 - offset
            index_data.iloc[
                position,
                index_data.columns.get_loc("Close"),
            ] = (
                index_data.iloc[position - 1]["Close"]
                * 0.995
            )
            proxy_volume[position] = (
                proxy_volume[position - 1] * 1.5
            )
        proxy = pd.DataFrame(
            {"Volume": proxy_volume},
            index=index,
        )
        result = calculate_market_status(
            index_data,
            proxy,
        )
        self.assertGreaterEqual(result["Distribution Days"], 5)
        self.assertEqual(
            result["Distribution Volume Source"],
            "NIFTYBEES",
        )

    def test_required_fundamentals_gate_blocks_failure(self) -> None:
        report = pd.DataFrame([{"Symbol": "GOOD"}, {"Symbol": "WEAK"}])
        source = pd.DataFrame(
            [
                {
                    "Symbol": "GOOD",
                    "As Of Date": date.today().isoformat(),
                    "EPS Growth YoY %": 35,
                    "Previous EPS Growth YoY %": 20,
                    "Sales Growth YoY %": 25,
                    "Operating Margin %": 18,
                    "Previous Operating Margin %": 16,
                },
                {
                    "Symbol": "WEAK",
                    "As Of Date": date.today().isoformat(),
                    "EPS Growth YoY %": 5,
                    "Previous EPS Growth YoY %": 10,
                    "Sales Growth YoY %": 4,
                    "Operating Margin %": 12,
                    "Previous Operating Margin %": 14,
                },
            ]
        )
        with patch("fundamentals.FUNDAMENTALS_GATE_MODE", "required"):
            result = add_fundamentals_gate(report, source)
        self.assertTrue(bool(result.loc[0, "Fundamentals Eligible"]))
        self.assertFalse(bool(result.loc[1, "Fundamentals Eligible"]))

    def test_base_stage_advances_only_after_breakout_and_new_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "base.json"
            first = pd.DataFrame(
                [
                    {
                        "Symbol": "ABC",
                        "Primary Pattern": "Flat Base",
                        "Pattern Pivot Price": 100.0,
                        "Current Price": 101.0,
                    }
                ]
            )
            with patch("base_stage.BASE_STAGE_ENABLED", True):
                result1 = add_base_stage_tracking(
                    first,
                    state_file=state,
                    as_of=date(2026, 1, 1),
                )
                second = first.copy()
                second["Pattern Pivot Price"] = 110.0
                second["Current Price"] = 108.0
                result2 = add_base_stage_tracking(
                    second,
                    state_file=state,
                    as_of=date(2026, 1, 1)
                    + timedelta(days=25),
                )
            self.assertEqual(result1.loc[0, "Base Stage"], 1)
            self.assertEqual(result2.loc[0, "Base Stage"], 2)

    def test_failed_required_fundamentals_blocks_trade_action(self) -> None:
        report = pd.DataFrame(
            [
                {
                    "Current Price": 100.1,
                    "Suggested Entry": 100.0,
                    "Suggested Stop Loss": 95.0,
                    "Stop Loss %": 5.0,
                    "Trade Quality Score": 95.0,
                    "RS Score": 95.0,
                    "Sector RS Score": 95.0,
                    "VCP Score": 95.0,
                    "Volume Score": 95.0,
                    "EMA Bullish Alignment": True,
                    "20D Avg Volume": 1_000_000,
                    "Current Volume": 2_000_000,
                    "Fundamentals Eligible": False,
                    "Fundamentals Gate Status": "FAIL - BLOCKED",
                }
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
        self.assertEqual(result.loc[0, "Action"], "AVOID")
        self.assertEqual(
            result.loc[0, "Trade Urgency"],
            "FUNDAMENTALS BLOCK",
        )


if __name__ == "__main__":
    unittest.main()
