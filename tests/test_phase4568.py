import pandas as pd

from confirmation_engine import confirm, enrich
from live_breakout_engine import BreakoutState


def test_confirmation_confirmed():
    row = pd.Series({
        "State": "STRONG BREAKOUT",
        "Volume Ratio": 2.2,
        "Candle Confirmation": True,
        "RS Score": 85,
        "Trend Template Pass": True,
        "Breakout %": 2.0,
    })
    result = confirm(row)
    assert result.status == "CONFIRMED"
    assert result.score >= 75


def test_confirmation_failure():
    row = pd.Series({
        "State": "FAILED BREAKOUT",
        "Volume Ratio": 0.7,
        "Candle Confirmation": False,
        "Breakout %": 1.0,
    })
    result = confirm(row)
    assert result.status == "FAILED"


def test_enrich_preserves_rows():
    frame = pd.DataFrame([{"Symbol": "ABC", "State": "NEAR RESISTANCE", "Volume Ratio": 1.1, "Candle Confirmation": False}])
    out = enrich(frame)
    assert len(out) == 1
    assert "Confirmation Score" in out.columns
