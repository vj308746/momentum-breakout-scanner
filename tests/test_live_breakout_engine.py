import pandas as pd

from live_breakout_engine import evaluate_breakout


def make_frame(closes, volumes=None):
    volumes = volumes or [1000] * len(closes)
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="D", tz="UTC")
    close = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(
        {
            "Open": close - 0.2,
            "High": close + 0.5,
            "Low": close - 0.5,
            "Close": close,
            "Volume": volumes,
        },
        index=idx,
    )


def test_near_resistance_state():
    closes = [100] * 30 + [100.2]
    result = evaluate_breakout(make_frame(closes))
    assert result.state in {"NEAR RESISTANCE", "TESTING RESISTANCE"}


def test_confirmed_breakout_state():
    closes = [100] * 30 + [102]
    volumes = [1000] * 30 + [2200]
    result = evaluate_breakout(make_frame(closes, volumes))
    assert result.state in {"CONFIRMED BREAKOUT", "STRONG BREAKOUT"}
    assert result.candle_confirmation
    assert result.volume_ratio > 2


def test_failed_breakout_state():
    closes = [100] * 29 + [103, 98.5]
    volumes = [1000] * 29 + [2200, 1800]
    result = evaluate_breakout(make_frame(closes, volumes))
    assert result.state == "FAILED BREAKOUT"
