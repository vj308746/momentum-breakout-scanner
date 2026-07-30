from __future__ import annotations

from typing import Any

import pandas as pd

from config import (
    HTF_FLAG_MAX_DAYS,
    HTF_FLAG_MIN_DAYS,
    HTF_FLAG_MAX_SLOPE_PCT,
    HTF_FLAG_MIN_SLOPE_PCT,
    HTF_FLAG_VOLUME_DRYUP_RATIO,
    HTF_MAX_DISTANCE_TO_PIVOT_PCT,
    HTF_MAX_FLAG_DEPTH_PCT,
    HTF_MIN_RISE_PCT,
    HTF_RISE_DAYS,
    PATTERN_MIN_CONFIDENCE,
)
from patterns.common import (
    bounded_score,
    clean_ohlcv,
    depth_pct,
    distance_to_pivot,
    linear_slope_pct,
    pct_change,
)


def detect_high_tight_flag(data: pd.DataFrame) -> dict[str, Any]:
    frame = clean_ohlcv(
        data,
        HTF_RISE_DAYS + HTF_FLAG_MAX_DAYS + 5,
    )
    best: dict[str, Any] | None = None

    for flag_days in range(HTF_FLAG_MIN_DAYS, HTF_FLAG_MAX_DAYS + 1):
        flag = frame.tail(flag_days)
        rise = frame.iloc[-(flag_days + HTF_RISE_DAYS):-flag_days]
        third = max(2, len(rise) // 3)
        start_zone = rise.iloc[:third]
        end_zone = rise.iloc[-third:]
        start_index = start_zone["Low"].idxmin()
        end_index = end_zone["High"].idxmax()
        start_position = int(rise.index.get_loc(start_index))
        end_position = int(rise.index.get_loc(end_index))
        chronological = start_position < end_position
        rise_pct = pct_change(
            float(rise.loc[end_index, "High"]),
            float(rise.loc[start_index, "Low"]),
        )

        pivot = float(flag["High"].max())
        flag_depth = depth_pct(pivot, float(flag["Low"].min()))
        flag_slope = linear_slope_pct(flag["Close"])
        volume_ratio = float(
            flag["Volume"].mean() / max(rise["Volume"].mean(), 1.0)
        )
        close = float(flag["Close"].iloc[-1])
        distance = distance_to_pivot(close, pivot)

        rise_pass = chronological and rise_pct >= HTF_MIN_RISE_PCT
        depth_pass = flag_depth <= HTF_MAX_FLAG_DEPTH_PCT
        volume_pass = volume_ratio <= HTF_FLAG_VOLUME_DRYUP_RATIO
        slope_pass = (
            HTF_FLAG_MIN_SLOPE_PCT
            <= flag_slope
            <= HTF_FLAG_MAX_SLOPE_PCT
        )
        distance_pass = (
            -3.0
            <= distance
            <= HTF_MAX_DISTANCE_TO_PIVOT_PCT
        )
        mandatory_pass = (
            rise_pass
            and depth_pass
            and volume_pass
            and slope_pass
            and distance_pass
        )
        rise_quality = (
            25
            + 10
            * min(
                1.0,
                max(
                    0.0,
                    (
                        rise_pct
                        - HTF_MIN_RISE_PCT
                    )
                    / max(HTF_MIN_RISE_PCT, 1.0),
                ),
            )
            if rise_pass
            else 0
        )
        depth_quality = (
            12
            + 8
            * max(
                0.0,
                1.0
                - flag_depth
                / max(HTF_MAX_FLAG_DEPTH_PCT, 1.0),
            )
            if depth_pass
            else 0
        )
        volume_quality = (
            10
            + 5
            * max(
                0.0,
                (
                    HTF_FLAG_VOLUME_DRYUP_RATIO
                    - volume_ratio
                )
                / max(HTF_FLAG_VOLUME_DRYUP_RATIO, 0.01),
            )
            if volume_pass
            else 0
        )
        slope_quality = (
            7
            + 3
            * max(
                0.0,
                1.0
                - abs(flag_slope)
                / max(
                    abs(HTF_FLAG_MIN_SLOPE_PCT),
                    abs(HTF_FLAG_MAX_SLOPE_PCT),
                    0.01,
                ),
            )
            if slope_pass
            else 0
        )
        distance_quality = (
            10
            + 5
            * max(
                0.0,
                1.0
                - abs(distance)
                / max(
                    HTF_MAX_DISTANCE_TO_PIVOT_PCT,
                    1.0,
                ),
            )
            if distance_pass
            else 0
        )
        score = bounded_score(
            rise_quality
            + depth_quality
            + volume_quality
            + slope_quality
            + distance_quality
        )
        matched = mandatory_pass and score >= PATTERN_MIN_CONFIDENCE
        candidate = {
            "High Tight Flag Match": bool(matched),
            "High Tight Flag Mandatory Pass": bool(mandatory_pass),
            "High Tight Flag Confidence": score,
            "High Tight Flag Pivot Price": round(pivot, 2),
            "High Tight Flag Rise %": round(rise_pct, 2),
            "High Tight Flag Chronological Rise": chronological,
            "High Tight Flag Depth %": round(flag_depth, 2),
            "High Tight Flag Days": flag_days,
            "High Tight Flag Volume Ratio": round(volume_ratio, 2),
            "High Tight Flag Slope %": round(flag_slope, 3),
            "High Tight Flag Distance %": round(distance, 2),
            "High Tight Flag Reason": (
                f"chronological rise {chronological}, advance {rise_pct:.1f}%, "
                f"flag depth {flag_depth:.1f}%, slope {flag_slope:.3f}%, "
                f"volume ratio {volume_ratio:.2f}"
            ),
        }
        if best is None or score > float(best["High Tight Flag Confidence"]):
            best = candidate

    return best or {
        "High Tight Flag Match": False,
        "High Tight Flag Mandatory Pass": False,
        "High Tight Flag Confidence": 0.0,
        "High Tight Flag Pivot Price": 0.0,
        "High Tight Flag Reason": "No valid high tight flag",
    }
