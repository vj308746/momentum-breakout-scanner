from __future__ import annotations

from typing import Any

import pandas as pd

from config import (
    EP_GAP_MIN_PCT,
    EP_PRIOR_BASE_DAYS,
    EP_PRIOR_BASE_MAX_DEPTH_PCT,
    EP_VOLUME_MIN_RATIO,
)
from patterns.common import (
    base_result,
    bounded_score,
    clean_ohlcv,
    depth_pct,
)


PREFIX = "Episodic Pivot"


def detect_episodic_pivot(
    data: pd.DataFrame,
) -> dict[str, Any]:
    frame = clean_ohlcv(
        data,
        minimum=EP_PRIOR_BASE_DAYS + 22,
    )
    event = frame.iloc[-1]
    previous = frame.iloc[-2]
    prior_base = frame.iloc[
        -(EP_PRIOR_BASE_DAYS + 1):-1
    ]
    volume_baseline = frame["Volume"].iloc[-21:-1]

    previous_close = float(previous["Close"])
    gap_pct = (
        (float(event["Open"]) / previous_close - 1) * 100
        if previous_close > 0
        else 0.0
    )
    average_volume = float(volume_baseline.mean())
    volume_ratio = (
        float(event["Volume"]) / average_volume
        if average_volume > 0
        else 0.0
    )
    prior_high = float(prior_base["High"].max())
    prior_low = float(prior_base["Low"].min())
    base_depth = depth_pct(prior_high, prior_low)
    breakout = float(event["Close"]) > prior_high
    strong_close = float(event["Close"]) >= float(event["Open"])

    mandatory = (
        gap_pct >= EP_GAP_MIN_PCT
        and volume_ratio >= EP_VOLUME_MIN_RATIO
        and base_depth <= EP_PRIOR_BASE_MAX_DEPTH_PCT
        and breakout
        and strong_close
    )
    if not mandatory:
        result = base_result(
            PREFIX,
            "Requires a 5%+ gap, 2x+ volume, prior base and close above resistance.",
        )
        result[f"{PREFIX} Mandatory Pass"] = False
        return result

    score = (
        55
        + min(15, (gap_pct - EP_GAP_MIN_PCT) * 2)
        + min(15, (volume_ratio - EP_VOLUME_MIN_RATIO) * 7.5)
        + max(0, 10 - base_depth * 0.3)
    )
    return {
        f"{PREFIX} Match": True,
        f"{PREFIX} Mandatory Pass": True,
        f"{PREFIX} Confidence": bounded_score(score),
        f"{PREFIX} Pivot Price": round(prior_high, 2),
        f"{PREFIX} Reason": (
            f"Gap {gap_pct:.1f}%, volume {volume_ratio:.1f}x, "
            f"prior-base depth {base_depth:.1f}%."
        ),
        "Episodic Pivot Gap %": round(gap_pct, 2),
        "Episodic Pivot Volume Ratio": round(volume_ratio, 2),
    }
