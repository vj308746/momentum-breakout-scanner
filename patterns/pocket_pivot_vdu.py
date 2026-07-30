from __future__ import annotations

from typing import Any

import pandas as pd

from config import (
    PATTERN_MIN_CONFIDENCE,
    POCKET_PIVOT_LOOKBACK_DAYS,
    POCKET_PIVOT_MAX_DISTANCE_PCT,
    POCKET_PIVOT_MIN_VOLUME_RATIO,
    POCKET_PIVOT_RECENT_DAYS,
    VDU_BASELINE_DAYS,
    VDU_MAX_RATIO,
    VDU_RECENT_DAYS,
)
from patterns.common import (
    bounded_score,
    clean_ohlcv,
    distance_to_pivot,
)


def detect_pocket_pivot_vdu(data: pd.DataFrame) -> dict[str, Any]:
    frame = clean_ohlcv(data, VDU_BASELINE_DAYS + 15).copy()
    close = frame["Close"]
    up_day = close.diff() > 0
    down_volume = frame["Volume"].where(~up_day, 0.0)
    recent = frame.tail(POCKET_PIVOT_RECENT_DAYS)
    pocket_found = False
    pivot_price = 0.0
    pocket_ratio = 0.0
    for index in recent.index[::-1]:
        pos = frame.index.get_loc(index)
        if pos < POCKET_PIVOT_LOOKBACK_DAYS:
            continue
        row = frame.loc[index]
        prior = frame.iloc[pos - POCKET_PIVOT_LOOKBACK_DAYS:pos]
        max_down = float(down_volume.iloc[pos - POCKET_PIVOT_LOOKBACK_DAYS:pos].max())
        if (
            max_down > 0
            and float(row["Close"]) > float(row["Open"])
            and float(row["Volume"]) > max_down
        ):
            pocket_found = True
            pivot_price = float(row["High"])
            pocket_ratio = float(row["Volume"]) / max(max_down, 1.0)
            break
    baseline = frame["Volume"].iloc[-(VDU_BASELINE_DAYS + VDU_RECENT_DAYS):-VDU_RECENT_DAYS]
    recent_volume = frame["Volume"].tail(VDU_RECENT_DAYS)
    vdu_ratio = float(recent_volume.mean() / max(baseline.mean(), 1.0))
    vdu_pass = vdu_ratio <= VDU_MAX_RATIO
    ema10 = float(close.ewm(span=10, adjust=False).mean().iloc[-1])
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    current = float(close.iloc[-1])
    trend_pass = current > ema10 > ema20
    distance = distance_to_pivot(current, pivot_price)
    pocket_volume_pass = pocket_ratio >= POCKET_PIVOT_MIN_VOLUME_RATIO
    distance_pass = (
        pocket_found
        and -3.0 <= distance <= POCKET_PIVOT_MAX_DISTANCE_PCT
    )
    mandatory_pass = (
        pocket_found
        and pocket_volume_pass
        and vdu_pass
        and trend_pass
        and distance_pass
    )
    pocket_quality = (
        20
        + 10
        * min(
            1.0,
            max(
                0.0,
                pocket_ratio
                - POCKET_PIVOT_MIN_VOLUME_RATIO,
            ),
        )
        if pocket_found and pocket_volume_pass
        else 0
    )
    vdu_quality = (
        15
        + 10
        * max(
            0.0,
            (
                VDU_MAX_RATIO
                - vdu_ratio
            )
            / max(VDU_MAX_RATIO, 0.01),
        )
        if vdu_pass
        else 0
    )
    trend_quality = 20 if trend_pass else 0
    distance_quality = (
        10
        + 5
        * max(
            0.0,
            1.0
            - abs(distance)
            / max(POCKET_PIVOT_MAX_DISTANCE_PCT, 1.0),
        )
        if distance_pass
        else 0
    )
    score = bounded_score(
        pocket_quality
        + vdu_quality
        + trend_quality
        + distance_quality
    )
    matched = mandatory_pass and score >= PATTERN_MIN_CONFIDENCE
    return {
        "Pocket Pivot VDU Match": bool(matched),
        "Pocket Pivot VDU Mandatory Pass": bool(mandatory_pass),
        "Pocket Pivot VDU Confidence": score,
        "Pocket Pivot VDU Pivot Price": round(pivot_price, 2),
        "Pocket Pivot Found": pocket_found,
        "Pocket Pivot Volume Ratio": round(pocket_ratio, 2),
        "VDU Pass": vdu_pass,
        "VDU Ratio": round(vdu_ratio, 2),
        "Pocket Pivot VDU Distance %": round(distance, 2),
        "Pocket Pivot VDU Reason": f"pocket pivot {pocket_found}, VDU ratio {vdu_ratio:.2f}, EMA trend {trend_pass}",
    }
