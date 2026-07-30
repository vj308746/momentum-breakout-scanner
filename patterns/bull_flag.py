from __future__ import annotations

from typing import Any

import pandas as pd

from config import (
    BULL_FLAG_MAX_DAYS,
    BULL_FLAG_MAX_DEPTH_PCT,
    BULL_FLAG_MAX_DISTANCE_TO_PIVOT_PCT,
    BULL_FLAG_MAX_POLE_GAIN_PCT,
    BULL_FLAG_MAX_SLOPE_PCT,
    BULL_FLAG_MIN_DAYS,
    BULL_FLAG_MIN_POLE_GAIN_PCT,
    BULL_FLAG_MIN_SLOPE_PCT,
    BULL_FLAG_POLE_DAYS,
    BULL_FLAG_VOLUME_DRYUP_RATIO,
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


def detect_bull_flag(data: pd.DataFrame) -> dict[str, Any]:
    frame = clean_ohlcv(
        data,
        BULL_FLAG_POLE_DAYS + BULL_FLAG_MAX_DAYS + 10,
    )
    best: dict[str, Any] | None = None

    for flag_days in range(BULL_FLAG_MIN_DAYS, BULL_FLAG_MAX_DAYS + 1):
        flag = frame.tail(flag_days)
        pole = frame.iloc[-(flag_days + BULL_FLAG_POLE_DAYS):-flag_days]
        third = max(2, len(pole) // 3)

        # Enforce a real chronological advance: the launch low must occur in
        # the early pole and the peak must occur in its final third.
        start_zone = pole.iloc[:third]
        end_zone = pole.iloc[-third:]
        start_index = start_zone["Low"].idxmin()
        end_index = end_zone["High"].idxmax()
        start_position = int(pole.index.get_loc(start_index))
        end_position = int(pole.index.get_loc(end_index))
        start_low = float(pole.loc[start_index, "Low"])
        end_high = float(pole.loc[end_index, "High"])
        chronological = start_position < end_position
        pole_gain = pct_change(end_high, start_low)

        pivot = float(flag["High"].max())
        flag_depth = depth_pct(pivot, float(flag["Low"].min()))
        volume_ratio = float(
            flag["Volume"].mean() / max(pole["Volume"].mean(), 1.0)
        )
        flag_slope = linear_slope_pct(flag["Close"])
        close = float(flag["Close"].iloc[-1])
        distance = distance_to_pivot(close, pivot)

        pole_pass = (
            chronological
            and BULL_FLAG_MIN_POLE_GAIN_PCT
            <= pole_gain
            <= BULL_FLAG_MAX_POLE_GAIN_PCT
        )
        depth_pass = flag_depth <= BULL_FLAG_MAX_DEPTH_PCT
        volume_pass = volume_ratio <= BULL_FLAG_VOLUME_DRYUP_RATIO
        slope_pass = (
            BULL_FLAG_MIN_SLOPE_PCT
            <= flag_slope
            <= BULL_FLAG_MAX_SLOPE_PCT
        )
        distance_pass = (
            -3.0
            <= distance
            <= BULL_FLAG_MAX_DISTANCE_TO_PIVOT_PCT
        )
        mandatory_pass = (
            pole_pass
            and depth_pass
            and volume_pass
            and slope_pass
            and distance_pass
        )

        pole_quality = (
            20
            + 10
            * min(
                1.0,
                max(
                    0.0,
                    (
                        pole_gain
                        - BULL_FLAG_MIN_POLE_GAIN_PCT
                    )
                    / max(
                        BULL_FLAG_MAX_POLE_GAIN_PCT
                        - BULL_FLAG_MIN_POLE_GAIN_PCT,
                        1.0,
                    ),
                ),
            )
            if pole_pass
            else 0
        )
        depth_quality = (
            12
            + 10
            * max(
                0.0,
                1.0
                - flag_depth
                / max(BULL_FLAG_MAX_DEPTH_PCT, 1.0),
            )
            if depth_pass
            else 0
        )
        volume_quality = (
            10
            + 8
            * max(
                0.0,
                (
                    BULL_FLAG_VOLUME_DRYUP_RATIO
                    - volume_ratio
                )
                / max(BULL_FLAG_VOLUME_DRYUP_RATIO, 0.01),
            )
            if volume_pass
            else 0
        )
        slope_quality = (
            8
            + 7
            * max(
                0.0,
                1.0
                - abs(flag_slope)
                / max(
                    abs(BULL_FLAG_MIN_SLOPE_PCT),
                    abs(BULL_FLAG_MAX_SLOPE_PCT),
                    0.01,
                ),
            )
            if slope_pass
            else 0
        )
        distance_quality = (
            8
            + 7
            * max(
                0.0,
                1.0
                - abs(distance)
                / max(
                    BULL_FLAG_MAX_DISTANCE_TO_PIVOT_PCT,
                    1.0,
                ),
            )
            if distance_pass
            else 0
        )
        score = bounded_score(
            pole_quality
            + depth_quality
            + volume_quality
            + slope_quality
            + distance_quality
        )
        matched = (
            mandatory_pass
            and score >= PATTERN_MIN_CONFIDENCE
        )
        candidate = {
            "Bull Flag Match": bool(matched),
            "Bull Flag Mandatory Pass": bool(mandatory_pass),
            "Bull Flag Confidence": score,
            "Bull Flag Pivot Price": round(pivot, 2),
            "Bull Flag Pole Gain %": round(pole_gain, 2),
            "Bull Flag Chronological Pole": chronological,
            "Bull Flag Depth %": round(flag_depth, 2),
            "Bull Flag Days": flag_days,
            "Bull Flag Volume Ratio": round(volume_ratio, 2),
            "Bull Flag Slope %": round(flag_slope, 3),
            "Bull Flag Distance %": round(distance, 2),
            "Bull Flag Reason": (
                f"chronological pole {chronological}, pole {pole_gain:.1f}%, "
                f"flag depth {flag_depth:.1f}%, slope {flag_slope:.3f}%, "
                f"volume ratio {volume_ratio:.2f}"
            ),
        }
        if best is None or score > float(best["Bull Flag Confidence"]):
            best = candidate

    return best or {
        "Bull Flag Match": False,
        "Bull Flag Mandatory Pass": False,
        "Bull Flag Confidence": 0.0,
        "Bull Flag Pivot Price": 0.0,
        "Bull Flag Reason": "No valid flag",
    }
