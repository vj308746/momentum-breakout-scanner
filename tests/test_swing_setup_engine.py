import numpy as np
import pandas as pd

from swing_setup_engine import calculate_swing_setup_metrics


def make_data(n=260):
    rng = np.random.default_rng(7)
    close = np.linspace(100, 180, n) + rng.normal(0, 1.0, n)
    # Construct a consolidation/support area near the latest price.
    close[-20:] = np.array([171, 173, 171.5, 172, 170.8, 172.5, 173.2, 172.1, 174, 173.5, 174.2, 175, 174.4, 175.5, 176, 175.2, 176.5, 177, 176.8, 177.5])
    high = close + 1.5
    low = close - 1.5
    low[-10] = 173.0
    volume = np.full(n, 100000.0)
    volume[-1] = 110000
    return pd.DataFrame({"Open": close - 0.5, "High": high, "Low": low, "Close": close, "Volume": volume})


def test_returns_swing_fields():
    result = calculate_swing_setup_metrics(make_data())
    assert "Swing Setup Score" in result
    assert "Support Price" in result
    assert "Pivot Resistance" in result
    assert result["Swing Setup Score"] >= 0


def test_red_high_volume_bar_is_not_constructive():
    df = make_data()
    df.loc[df.index[-1], "Open"] = df.loc[df.index[-1], "Close"] + 2
    df.loc[df.index[-1], "Volume"] = 500000
    result = calculate_swing_setup_metrics(df)
    assert result["Constructive Volume"] is False
    assert result["Support Price Behaviour"] == "SELLING PRESSURE"
