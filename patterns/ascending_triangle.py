from __future__ import annotations

from typing import Any

import pandas as pd

from config import (
    ASC_TRIANGLE_LOOKBACK_DAYS,
    ASC_TRIANGLE_MAX_RESISTANCE_SLOPE_PCT,
    ASC_TRIANGLE_MIN_LOW_SLOPE_PCT,
    ASC_TRIANGLE_MIN_TOUCHES,
    ASC_TRIANGLE_RESISTANCE_TOLERANCE_PCT,
    PATTERN_MIN_CONFIDENCE,
)
from patterns.common import bounded_score, clean_ohlcv, distance_to_pivot, linear_slope_pct


def detect_ascending_triangle(data: pd.DataFrame) -> dict[str, Any]:
    frame = clean_ohlcv(data, ASC_TRIANGLE_LOOKBACK_DAYS).tail(ASC_TRIANGLE_LOOKBACK_DAYS)
    pivot = float(frame["High"].quantile(0.95))
    tolerance = pivot * ASC_TRIANGLE_RESISTANCE_TOLERANCE_PCT / 100.0
    touches = int(((frame["High"] - pivot).abs() <= tolerance).sum())
    # Rolling lows reduce single-day noise.
    low_curve = frame["Low"].rolling(5).min().dropna()
    low_slope = linear_slope_pct(low_curve)
    high_curve = frame["High"].rolling(5).max().dropna()
    resistance_slope = linear_slope_pct(high_curve)
    resistance_spread = float(frame["High"].nlargest(max(ASC_TRIANGLE_MIN_TOUCHES, 3)).std() / max(pivot, 1.0) * 100)
    close = float(frame["Close"].iloc[-1])
    distance = distance_to_pivot(close, pivot)
    touches_pass = touches >= ASC_TRIANGLE_MIN_TOUCHES
    slope_pass = low_slope >= ASC_TRIANGLE_MIN_LOW_SLOPE_PCT
    resistance_pass = (
        abs(resistance_slope)
        <= ASC_TRIANGLE_MAX_RESISTANCE_SLOPE_PCT
    )
    touches_quality = (
        18
        + min(
            12.0,
            max(
                0,
                touches - ASC_TRIANGLE_MIN_TOUCHES,
            )
            * 4.0,
        )
        if touches_pass
        else 0
    )
    lows_quality = (
        15
        + 10
        * min(
            1.0,
            low_slope
            / max(
                ASC_TRIANGLE_MIN_LOW_SLOPE_PCT * 4,
                0.01,
            ),
        )
        if slope_pass
        else 0
    )
    resistance_quality = (
        12
        + 8
        * max(
            0.0,
            1.0
            - resistance_spread
            / max(
                ASC_TRIANGLE_RESISTANCE_TOLERANCE_PCT,
                0.01,
            ),
        )
        if resistance_pass
        else 0
    )
    distance_quality = (
        10
        + 5
        * max(0.0, 1.0 - abs(distance) / 5.0)
        if -3 <= distance <= 5
        else 0
    )
    score = bounded_score(
        touches_quality
        + lows_quality
        + resistance_quality
        + distance_quality
    )
    distance_pass = -3.0 <= distance <= 5.0
    mandatory_pass = (
        touches_pass
        and slope_pass
        and resistance_pass
        and distance_pass
    )
    matched = (
        mandatory_pass
        and score >= PATTERN_MIN_CONFIDENCE
    )
    return {
        "Ascending Triangle Match": bool(matched),
        "Ascending Triangle Mandatory Pass": bool(mandatory_pass),
        "Ascending Triangle Confidence": score,
        "Ascending Triangle Pivot Price": round(pivot, 2),
        "Ascending Triangle Touches": touches,
        "Ascending Triangle Low Slope %": round(low_slope, 3),
        "Ascending Triangle Resistance Spread %": round(resistance_spread, 2),
        "Ascending Triangle Resistance Slope %": round(resistance_slope, 3),
        "Ascending Triangle Distance %": round(distance, 2),
        "Ascending Triangle Reason": (
            f"{touches} resistance touches, "
            f"rising-low slope {low_slope:.3f}%, "
            f"resistance slope {resistance_slope:.3f}%"
        ),
    }
