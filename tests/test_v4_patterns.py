from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from decision_engine import add_trade_decisions
from pattern_engine import (
    PATTERN_SPECS,
    analyse_patterns,
    finalise_pattern_columns,
    select_pattern_trade_setup,
)
from trend_template import analyse_stock
from trade_planner import calculate_trade_plan
from patterns.bull_flag import detect_bull_flag


def sample_ohlcv(rows: int = 320) -> pd.DataFrame:
    x = np.arange(rows, dtype=float)
    close = 100.0 + x * 0.22 + np.sin(x / 7.0) * 2.0
    volume = 1_000_000.0 + (np.cos(x / 9.0) + 1.0) * 100_000.0
    return pd.DataFrame(
        {
            "Open": close - 0.4,
            "High": close + 1.2,
            "Low": close - 1.2,
            "Close": close,
            "Volume": volume,
        },
        index=pd.date_range("2025-01-01", periods=rows, freq="B"),
    )


def bull_flag_sample(flag_volume: float) -> pd.DataFrame:
    pre = np.linspace(90.0, 100.0, 40)
    pole = np.linspace(100.0, 130.0, 20)
    flag = np.linspace(129.0, 126.0, 10)
    close = np.concatenate([pre, pole, flag])
    volume = np.concatenate(
        [
            np.full(40, 800_000.0),
            np.full(20, 1_500_000.0),
            np.full(10, flag_volume),
        ]
    )
    return pd.DataFrame(
        {
            "Open": close - 0.3,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": volume,
        }
    )


class PatternEngineTests(unittest.TestCase):
    def test_all_detectors_return_shared_schema(self) -> None:
        metrics = analyse_patterns(sample_ohlcv())
        self.assertEqual(len(PATTERN_SPECS), 8)
        self.assertNotIn(
            "Bull Flag",
            [name for name, _, _ in PATTERN_SPECS],
        )
        for _, prefix, _ in PATTERN_SPECS:
            self.assertIn(f"{prefix} Match", metrics)
            self.assertIn(f"{prefix} Mandatory Pass", metrics)
            self.assertIn(f"{prefix} Confidence", metrics)
            self.assertIn(f"{prefix} Pivot Price", metrics)
            self.assertIn(f"{prefix} Reason", metrics)
            self.assertLessEqual(
                float(metrics[f"{prefix} Confidence"]),
                98.0,
            )

    def test_primary_pattern_selects_highest_confidence(self) -> None:
        metrics = {
            "Trend Template Pass": True,
            "VCP Pass": False,
            "Pivot Price": 105.0,
        }
        for _, prefix, _ in PATTERN_SPECS:
            metrics[f"{prefix} Match"] = False
            metrics[f"{prefix} Mandatory Pass"] = False
            metrics[f"{prefix} Confidence"] = 0.0
            metrics[f"{prefix} Pivot Price"] = 0.0
        metrics.update(
            {
                "Flat Base Match": True,
                "Flat Base Mandatory Pass": True,
                "Flat Base Confidence": 78.0,
                "Flat Base Pivot Price": 121.0,
                "High Tight Flag Match": True,
                "High Tight Flag Mandatory Pass": True,
                "High Tight Flag Confidence": 91.0,
                "High Tight Flag Pivot Price": 123.0,
            }
        )
        selected = select_pattern_trade_setup(metrics)
        self.assertEqual(selected["Primary Pattern"], "High Tight Flag")
        self.assertEqual(selected["Pattern Count"], 2)
        self.assertEqual(selected["Pattern Pivot Price"], 123.0)

    def test_young_ipo_uses_adapted_trend_template(self) -> None:
        data = sample_ohlcv(90)
        result = analyse_stock("TESTIPO", "Test IPO", "Technology", data)
        self.assertEqual(result["Trend Template Type"], "IPO Adapted")
        self.assertTrue(result["Trend Template Pass"])

    def test_selected_pattern_pivot_reaches_trade_planner(self) -> None:
        data = sample_ohlcv()
        selected = {
            "Pattern Pivot Price": float(data["High"].tail(20).max()),
        }
        plan = calculate_trade_plan(
            data=data,
            pivot_price=selected["Pattern Pivot Price"],
        )
        self.assertGreater(plan["Suggested Entry"], 0)
        self.assertGreater(plan["Suggested Stop Loss"], 0)
        self.assertGreaterEqual(plan["Suggested Quantity"], 0)

    def test_generic_rising_series_is_not_a_bull_flag(self) -> None:
        metrics = detect_bull_flag(sample_ohlcv())
        self.assertFalse(metrics["Bull Flag Match"])

    def test_pocket_pivot_requires_vdu(self) -> None:
        metrics = analyse_patterns(sample_ohlcv())
        if not metrics["VDU Pass"]:
            self.assertFalse(metrics["Pocket Pivot VDU Match"])

    def test_minervini_category_is_preserved(self) -> None:
        report = pd.DataFrame(
            [
                {
                    "Matched Patterns": "Flat Base, Minervini VCP",
                    "Pattern Count": 2,
                    "Pattern Confidence": 98.0,
                    "Primary Pattern": "Flat Base",
                    "VCP Score": 80.0,
                    "Trend + RS + Volume + VCP Pass": True,
                }
            ]
        )
        result = finalise_pattern_columns(report)
        self.assertEqual(result.loc[0, "Qualified Scanner"], "Minervini")
        self.assertEqual(result.loc[0, "Primary Pattern"], "Minervini VCP")

    def test_partial_vcp_is_not_a_v4_pattern(self) -> None:
        metrics = {
            "Trend Template Pass": True,
            "VCP Pass": True,
            "VCP Score": 80.0,
            "Pivot Price": 120.0,
        }
        for _, prefix, _ in PATTERN_SPECS:
            metrics[f"{prefix} Match"] = False
            metrics[f"{prefix} Mandatory Pass"] = False
            metrics[f"{prefix} Confidence"] = 0.0
            metrics[f"{prefix} Pivot Price"] = 0.0
        selected = select_pattern_trade_setup(metrics)
        self.assertFalse(selected["Any Pattern Match"])
        self.assertEqual(selected["Pattern Count"], 0)

    def test_bull_flag_confidence_is_graduated(self) -> None:
        strong = detect_bull_flag(bull_flag_sample(500_000.0))
        weaker = detect_bull_flag(bull_flag_sample(1_200_000.0))
        self.assertTrue(strong["Bull Flag Match"])
        self.assertTrue(weaker["Bull Flag Match"])
        self.assertGreater(
            strong["Bull Flag Confidence"],
            weaker["Bull Flag Confidence"],
        )
        self.assertLess(strong["Bull Flag Confidence"], 98.0)

    def test_near_trigger_is_downgraded_for_high_risk(self) -> None:
        report = pd.DataFrame(
            [
                {
                    "Current Price": 99.0,
                    "Suggested Entry": 100.0,
                    "Suggested Stop Loss": 92.0,
                    "Stop Loss %": 8.0,
                    "Trade Quality Score": 90.0,
                    "RS Score": 90.0,
                    "Sector RS Score": 90.0,
                    "VCP Score": 90.0,
                    "Volume Score": 90.0,
                    "EMA Bullish Alignment": True,
                    "20D Avg Volume": 1_000_000,
                    "Current Volume": 1_500_000,
                }
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


if __name__ == "__main__":
    unittest.main()
