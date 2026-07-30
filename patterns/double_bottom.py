from __future__ import annotations

from typing import Any

import pandas as pd

from config import (
    DOUBLE_BOTTOM_LOOKBACK_DAYS,
    DOUBLE_BOTTOM_MAX_DEPTH_PCT,
    DOUBLE_BOTTOM_MAX_LOW_DIFFERENCE_PCT,
    DOUBLE_BOTTOM_MIN_SEPARATION_DAYS,
    DOUBLE_BOTTOM_UNDERCUT_TOLERANCE_PCT,
    PATTERN_MIN_CONFIDENCE,
)
from patterns.common import bounded_score, clean_ohlcv, depth_pct, distance_to_pivot


def detect_double_bottom(data: pd.DataFrame) -> dict[str, Any]:
    frame = clean_ohlcv(data, 70).tail(DOUBLE_BOTTOM_LOOKBACK_DAYS).reset_index(drop=True)
    n = len(frame)
    first_zone = frame.iloc[: n // 2]
    second_zone = frame.iloc[n // 2 :]
    first_pos = int(first_zone["Low"].idxmin())
    second_pos = int(second_zone["Low"].idxmin())
    first_low = float(frame.loc[first_pos, "Low"])
    second_low = float(frame.loc[second_pos, "Low"])
    separation = second_pos - first_pos
    if separation < DOUBLE_BOTTOM_MIN_SEPARATION_DAYS:
        return _empty("Bottoms too close")
    middle = frame.iloc[first_pos: second_pos + 1]
    pivot = float(middle["High"].max())
    peak_before = float(frame.iloc[: first_pos + 1]["High"].max())
    total_depth = depth_pct(max(peak_before, pivot), min(first_low, second_low))
    low_difference = abs(second_low - first_low) / max(first_low, 1.0) * 100
    undercut = (first_low - second_low) / max(first_low, 1.0) * 100
    close = float(frame["Close"].iloc[-1])
    distance = distance_to_pivot(close, pivot)
    lows_pass = low_difference <= DOUBLE_BOTTOM_MAX_LOW_DIFFERENCE_PCT
    undercut_pass = -2.0 <= undercut <= DOUBLE_BOTTOM_UNDERCUT_TOLERANCE_PCT
    lows_quality = (
        18
        + 12
        * max(
            0.0,
            1.0
            - low_difference
            / max(DOUBLE_BOTTOM_MAX_LOW_DIFFERENCE_PCT, 0.01),
        )
        if lows_pass
        else 0
    )
    undercut_quality = (
        12
        + 8
        * max(
            0.0,
            1.0
            - abs(undercut - 1.0)
            / max(DOUBLE_BOTTOM_UNDERCUT_TOLERANCE_PCT, 0.01),
        )
        if undercut_pass
        else 0
    )
    depth_pass = total_depth <= DOUBLE_BOTTOM_MAX_DEPTH_PCT
    depth_quality = (
        12
        + 8
        * max(
            0.0,
            1.0
            - total_depth
            / max(DOUBLE_BOTTOM_MAX_DEPTH_PCT, 1.0),
        )
        if depth_pass
        else 0
    )
    distance_quality = (
        8
        + 7
        * max(0.0, 1.0 - abs(distance) / 6.0)
        if -3 <= distance <= 6
        else 0
    )
    trend_quality = (
        15
        if close > float(frame["Close"].tail(20).mean())
        else 0
    )
    score = bounded_score(
        lows_quality
        + undercut_quality
        + depth_quality
        + distance_quality
        + trend_quality
    )
    distance_pass = -3.0 <= distance <= 6.0
    mandatory_pass = (
        lows_pass
        and undercut_pass
        and depth_pass
        and distance_pass
    )
    matched = mandatory_pass and score >= PATTERN_MIN_CONFIDENCE
    return {
        "Double Bottom Match": bool(matched),
        "Double Bottom Mandatory Pass": bool(mandatory_pass),
        "Double Bottom Confidence": score,
        "Double Bottom Pivot Price": round(pivot, 2),
        "Double Bottom First Low": round(first_low, 2),
        "Double Bottom Second Low": round(second_low, 2),
        "Double Bottom Low Difference %": round(low_difference, 2),
        "Double Bottom Separation Days": separation,
        "Double Bottom Depth %": round(total_depth, 2),
        "Double Bottom Distance %": round(distance, 2),
        "Double Bottom Reason": f"lows differ {low_difference:.1f}%, separation {separation} days, depth {total_depth:.1f}%",
    }


def _empty(reason: str) -> dict[str, Any]:
    return {
        "Double Bottom Match": False, "Double Bottom Confidence": 0.0,
        "Double Bottom Mandatory Pass": False,
        "Double Bottom Pivot Price": 0.0, "Double Bottom Reason": reason,
    }
