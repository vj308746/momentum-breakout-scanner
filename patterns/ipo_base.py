from __future__ import annotations

from typing import Any

import pandas as pd

from config import (
    IPO_BASE_MAX_DAYS,
    IPO_BASE_MAX_DEPTH_PCT,
    IPO_BASE_MAX_HISTORY_DAYS,
    IPO_BASE_MIN_DAYS,
    IPO_BASE_MIN_DEPTH_PCT,
    IPO_BASE_MIN_HISTORY_DAYS,
    PATTERN_MIN_CONFIDENCE,
)
from patterns.common import bounded_score, clean_ohlcv, depth_pct, distance_to_pivot


def detect_ipo_base(data: pd.DataFrame) -> dict[str, Any]:
    frame = clean_ohlcv(data, IPO_BASE_MIN_HISTORY_DAYS)
    history_days = len(frame)
    if history_days > IPO_BASE_MAX_HISTORY_DAYS:
        return _empty(f"Not a recent listing ({history_days} sessions)")
    best: dict[str, Any] | None = None
    max_days = min(IPO_BASE_MAX_DAYS, history_days)
    for days in range(IPO_BASE_MIN_DAYS, max_days + 1, 5):
        base = frame.tail(days)
        pivot = float(base["High"].max())
        low = float(base["Low"].min())
        depth = depth_pct(pivot, low)
        close = float(base["Close"].iloc[-1])
        distance = distance_to_pivot(close, pivot)
        recent_vol = float(base["Volume"].tail(5).mean())
        earlier_vol = float(base["Volume"].head(max(5, days - 5)).mean())
        volume_ratio = recent_vol / max(earlier_vol, 1.0)
        depth_pass = IPO_BASE_MIN_DEPTH_PCT <= depth <= IPO_BASE_MAX_DEPTH_PCT
        distance_pass = -3.0 <= distance <= 7.0
        volume_pass = volume_ratio <= 0.90
        mandatory_pass = depth_pass and distance_pass and volume_pass
        depth_midpoint = (
            IPO_BASE_MIN_DEPTH_PCT
            + IPO_BASE_MAX_DEPTH_PCT
        ) / 2
        depth_quality = (
            20
            + 15
            * max(
                0.0,
                1.0
                - abs(depth - depth_midpoint)
                / max(
                    (
                        IPO_BASE_MAX_DEPTH_PCT
                        - IPO_BASE_MIN_DEPTH_PCT
                    )
                    / 2,
                    1.0,
                ),
            )
            if depth_pass
            else 0
        )
        distance_quality = (
            15
            + 10
            * max(0.0, 1.0 - abs(distance) / 7.0)
            if distance_pass
            else 0
        )
        volume_quality = (
            10
            + 10
            * max(0.0, (0.90 - volume_ratio) / 0.90)
            if volume_pass
            else 0
        )
        close_quality = (
            15
            if close > float(base["Close"].mean())
            else 0
        )
        score = bounded_score(
            depth_quality
            + distance_quality
            + volume_quality
            + close_quality
        )
        matched = mandatory_pass and score >= PATTERN_MIN_CONFIDENCE
        candidate = {
            "IPO Base Match": bool(matched),
            "IPO Base Mandatory Pass": bool(mandatory_pass),
            "IPO Base Confidence": score,
            "IPO Base Pivot Price": round(pivot, 2),
            "IPO Base History Days": history_days,
            "IPO Base Days": days,
            "IPO Base Depth %": round(depth, 2),
            "IPO Base Volume Ratio": round(volume_ratio, 2),
            "IPO Base Distance %": round(distance, 2),
            "IPO Base Reason": f"listing history {history_days} sessions, base depth {depth:.1f}%",
        }
        if best is None or score > float(best["IPO Base Confidence"]):
            best = candidate
    return best or _empty("No valid IPO base")


def _empty(reason: str) -> dict[str, Any]:
    return {
        "IPO Base Match": False, "IPO Base Confidence": 0.0,
        "IPO Base Mandatory Pass": False,
        "IPO Base Pivot Price": 0.0, "IPO Base Reason": reason,
    }
