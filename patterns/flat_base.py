from __future__ import annotations

from typing import Any

import pandas as pd

from config import (
    FLAT_BASE_MAX_DAYS,
    FLAT_BASE_MAX_DEPTH_PCT,
    FLAT_BASE_MAX_DISTANCE_TO_PIVOT_PCT,
    FLAT_BASE_MIN_DAYS,
    FLAT_BASE_MIN_PRIOR_RISE_PCT,
    FLAT_BASE_VOLUME_DRYUP_RATIO,
    PATTERN_MIN_CONFIDENCE,
)
from patterns.common import bounded_score, clean_ohlcv, depth_pct, distance_to_pivot, pct_change


def detect_flat_base(data: pd.DataFrame) -> dict[str, Any]:
    frame = clean_ohlcv(data, FLAT_BASE_MIN_DAYS + 30)
    best: dict[str, Any] | None = None
    for days in range(FLAT_BASE_MIN_DAYS, min(FLAT_BASE_MAX_DAYS, len(frame) - 20) + 1, 5):
        base = frame.tail(days)
        prior = frame.iloc[-(days + 25):-days]
        high = float(base["High"].max())
        low = float(base["Low"].min())
        close = float(base["Close"].iloc[-1])
        depth = depth_pct(high, low)
        prior_rise = pct_change(float(base["Close"].iloc[0]), float(prior["Close"].iloc[0]))
        volume_ratio = float(base["Volume"].tail(10).mean() / max(prior["Volume"].mean(), 1.0))
        distance = distance_to_pivot(close, high)
        depth_pass = depth <= FLAT_BASE_MAX_DEPTH_PCT
        prior_rise_pass = prior_rise >= FLAT_BASE_MIN_PRIOR_RISE_PCT
        volume_pass = volume_ratio <= FLAT_BASE_VOLUME_DRYUP_RATIO
        distance_pass = -3.0 <= distance <= FLAT_BASE_MAX_DISTANCE_TO_PIVOT_PCT
        mandatory_pass = (
            depth_pass
            and prior_rise_pass
            and volume_pass
            and distance_pass
        )
        depth_quality = (
            18
            + 12
            * max(
                0.0,
                1.0
                - depth
                / max(FLAT_BASE_MAX_DEPTH_PCT, 1.0),
            )
            if depth_pass
            else 0
        )
        prior_quality = (
            15
            + 10
            * min(
                1.0,
                max(
                    0.0,
                    (
                        prior_rise
                        - FLAT_BASE_MIN_PRIOR_RISE_PCT
                    )
                    / max(
                        FLAT_BASE_MIN_PRIOR_RISE_PCT * 2,
                        1.0,
                    ),
                ),
            )
            if prior_rise_pass
            else 0
        )
        volume_quality = (
            10
            + 10
            * max(
                0.0,
                (
                    FLAT_BASE_VOLUME_DRYUP_RATIO
                    - volume_ratio
                )
                / max(FLAT_BASE_VOLUME_DRYUP_RATIO, 0.01),
            )
            if volume_pass
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
                    FLAT_BASE_MAX_DISTANCE_TO_PIVOT_PCT,
                    1.0,
                ),
            )
            if distance_pass
            else 0
        )
        close_quality = (
            10
            if close > float(base["Close"].mean())
            else 0
        )
        score = bounded_score(
            depth_quality
            + prior_quality
            + volume_quality
            + distance_quality
            + close_quality
        )
        matched = mandatory_pass and score >= PATTERN_MIN_CONFIDENCE
        candidate = {
            "Flat Base Match": bool(matched),
            "Flat Base Mandatory Pass": bool(mandatory_pass),
            "Flat Base Confidence": score,
            "Flat Base Pivot Price": round(high, 2),
            "Flat Base Depth %": round(depth, 2),
            "Flat Base Days": days,
            "Flat Base Volume Ratio": round(volume_ratio, 2),
            "Flat Base Distance %": round(distance, 2),
            "Flat Base Reason": f"depth {depth:.1f}%, prior rise {prior_rise:.1f}%, volume ratio {volume_ratio:.2f}",
        }
        if best is None or score > float(best["Flat Base Confidence"]):
            best = candidate
    return best or {
        "Flat Base Match": False, "Flat Base Confidence": 0.0,
        "Flat Base Mandatory Pass": False,
        "Flat Base Pivot Price": 0.0, "Flat Base Reason": "No valid base window",
    }
