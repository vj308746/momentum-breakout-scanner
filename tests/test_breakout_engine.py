from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from breakout_engine import (
    calculate_breakout_metrics,
    finalise_breakout_report,
    select_breakout_trade_setup,
)


def price_frame(
    last_close: float,
    last_volume: float,
) -> pd.DataFrame:
    close = np.full(80, 100.0)
    close[-1] = last_close
    volume = np.full(80, 1_000_000.0)
    volume[-1] = last_volume
    return pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": volume,
        },
        index=pd.date_range("2026-01-01", periods=80, freq="B"),
    )


class BreakoutEngineTests(unittest.TestCase):
    def test_price_and_volume_breakout_is_detected(self) -> None:
        metrics = calculate_breakout_metrics(
            price_frame(106.0, 2_000_000.0)
        )
        self.assertEqual(metrics["Breakout Status"], "BREAKOUT TODAY")
        self.assertTrue(metrics["Movement Scanner Eligible"])
        self.assertTrue(metrics["20D Breakout"])
        self.assertGreaterEqual(metrics["Historical Volume Ratio"], 1.2)

    def test_weak_volume_does_not_confirm_breakout_today(self) -> None:
        metrics = calculate_breakout_metrics(
            price_frame(106.0, 700_000.0)
        )
        self.assertNotEqual(metrics["Breakout Status"], "BREAKOUT TODAY")

    def test_movement_setup_can_replace_weaker_pattern(self) -> None:
        selected = select_breakout_trade_setup(
            {
                "Any Pattern Match": True,
                "Primary Pattern": "Flat Base",
                "Pattern Confidence": 70.0,
                "Pattern Pivot Price": 100.0,
                "Movement Scanner Eligible": True,
                "Breakout Score": 85.0,
                "Movement Pivot Price": 102.0,
                "Breakout Status": "BREAKOUT TODAY",
            }
        )
        self.assertEqual(selected["Primary Pattern"], "BREAKOUT TODAY")
        self.assertEqual(selected["Pattern Pivot Price"], 102.0)

    def test_rs_floor_applies_to_final_eligibility(self) -> None:
        report = pd.DataFrame(
            [
                {
                    "Any Pattern Match": False,
                    "Movement Scanner Eligible": True,
                    "RS Score": 75.0,
                    "Matched Patterns": "None",
                    "Pattern Count": 0,
                },
                {
                    "Any Pattern Match": True,
                    "Movement Scanner Eligible": False,
                    "RS Score": 40.0,
                    "Matched Patterns": "Flat Base",
                    "Pattern Count": 1,
                },
            ]
        )
        result = finalise_breakout_report(report)
        self.assertTrue(bool(result.loc[0, "Breakout Scanner Eligible"]))
        self.assertFalse(bool(result.loc[1, "Breakout Scanner Eligible"]))


if __name__ == "__main__":
    unittest.main()
