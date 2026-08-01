from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from config import (
    BREAKOUT_MAX_EXTENSION_PCT,
    BREAKOUT_MIN_DAILY_GAIN_PCT,
    BREAKOUT_MIN_RS_SCORE,
    BREAKOUT_MIN_VOLUME_RATIO,
    BREAKOUT_NEAR_PCT,
    BREAKOUT_RECENT_SESSIONS,
    MOMENTUM_MIN_5D_RETURN_PCT,
)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return default if pd.isna(result) else result


def _prior_high(data: pd.DataFrame, lookback: int, end: int) -> float:
    start = max(0, end - lookback)
    values = data["High"].iloc[start:end]
    return _number(values.max()) if not values.empty else 0.0


def _recent_breakout(data: pd.DataFrame) -> dict[str, Any]:
    start = max(21, len(data) - BREAKOUT_RECENT_SESSIONS)
    for position in range(len(data) - 1, start - 1, -1):
        pivot = _prior_high(data, 20, position)
        if pivot <= 0:
            continue
        close = _number(data["Close"].iloc[position])
        previous_close = _number(data["Close"].iloc[position - 1])
        baseline = _number(
            data["Volume"].iloc[max(0, position - 20):position].mean()
        )
        volume = _number(data["Volume"].iloc[position])
        ratio = volume / baseline if baseline > 0 else 0.0
        if (
            close > pivot
            and previous_close <= pivot
            and ratio >= BREAKOUT_MIN_VOLUME_RATIO
        ):
            return {
                "match": True,
                "days_ago": len(data) - 1 - position,
                "date": str(data.index[position].date())
                if hasattr(data.index[position], "date")
                else str(data.index[position]),
                "pivot": pivot,
                "ratio": ratio,
            }
    return {
        "match": False,
        "days_ago": -1,
        "date": "",
        "pivot": 0.0,
        "ratio": 0.0,
    }


def calculate_breakout_metrics(data: pd.DataFrame) -> dict[str, Any]:
    """Detect price-level breakouts, recent breakouts and momentum movement."""
    required = {"Open", "High", "Low", "Close", "Volume"}
    if len(data) < 55 or not required.issubset(data.columns):
        return {
            "Movement Scanner Eligible": False,
            "Breakout Status": "INSUFFICIENT DATA",
            "Breakout Score": 0.0,
            "Movement Pivot Price": 0.0,
        }

    frame = data.dropna(subset=list(required)).copy()
    current = _number(frame["Close"].iloc[-1])
    previous = _number(frame["Close"].iloc[-2])
    daily_gain = ((current / previous) - 1.0) * 100 if previous > 0 else 0.0
    five_day_base = _number(frame["Close"].iloc[-6])
    return_5d = (
        ((current / five_day_base) - 1.0) * 100
        if five_day_base > 0
        else 0.0
    )
    average_volume = _number(frame["Volume"].iloc[-21:-1].mean())
    current_volume = _number(frame["Volume"].iloc[-1])
    volume_ratio = current_volume / average_volume if average_volume > 0 else 0.0

    pivot_20 = _prior_high(frame, 20, len(frame) - 1)
    pivot_50 = _prior_high(frame, 50, len(frame) - 1)
    pivot_52w = _prior_high(frame, min(252, len(frame) - 1), len(frame) - 1)

    break_20 = current > pivot_20 > 0
    break_50 = current > pivot_50 > 0
    break_52w = current > pivot_52w > 0
    breakout_today = (
        (break_20 or break_50 or break_52w)
        and volume_ratio >= BREAKOUT_MIN_VOLUME_RATIO
    )

    available_pivots = [
        value
        for value in (pivot_20, pivot_50, pivot_52w)
        if value > current
    ]
    approaching_pivot = min(available_pivots) if available_pivots else 0.0
    distance_to_pivot = (
        (approaching_pivot - current) / approaching_pivot * 100
        if approaching_pivot > 0
        else 0.0
    )
    approaching = (
        approaching_pivot > 0
        and 0 <= distance_to_pivot <= BREAKOUT_NEAR_PCT
    )

    momentum_mover = (
        (
            daily_gain >= BREAKOUT_MIN_DAILY_GAIN_PCT
            and volume_ratio >= BREAKOUT_MIN_VOLUME_RATIO
        )
        or (
            return_5d >= MOMENTUM_MIN_5D_RETURN_PCT
            and current > _number(frame["Close"].tail(20).mean())
        )
    )
    recent = _recent_breakout(frame)

    if breakout_today:
        status = "BREAKOUT TODAY"
        pivot = max(
            value
            for value, matched in (
                (pivot_20, break_20),
                (pivot_50, break_50),
                (pivot_52w, break_52w),
            )
            if matched
        )
    elif bool(recent["match"]):
        status = "RECENT BREAKOUT"
        pivot = _number(recent["pivot"])
    elif momentum_mover:
        status = "MOMENTUM MOVER"
        pivot = max(pivot_20, 0.0)
    elif approaching:
        status = "APPROACHING BREAKOUT"
        pivot = approaching_pivot
    else:
        status = "NO ACTIVE BREAKOUT"
        pivot = max(pivot_20, 0.0)

    extension = ((current / pivot) - 1.0) * 100 if pivot > 0 else 0.0
    not_extended = extension <= BREAKOUT_MAX_EXTENSION_PCT
    eligible = (
        status
        in {
            "BREAKOUT TODAY",
            "RECENT BREAKOUT",
            "MOMENTUM MOVER",
            "APPROACHING BREAKOUT",
        }
        and not_extended
    )

    score = 0.0
    score += 30.0 if breakout_today else 0.0
    score += 22.0 if bool(recent["match"]) else 0.0
    score += 20.0 if momentum_mover else 0.0
    score += 15.0 if approaching else 0.0
    score += min(20.0, max(0.0, volume_ratio - 1.0) * 20.0)
    score += min(10.0, max(0.0, daily_gain))
    score = min(98.0, score)

    return {
        "Movement Scanner Eligible": eligible,
        "Breakout Status": status,
        "Breakout Score": round(score, 1),
        "Movement Pivot Price": round(pivot, 2),
        "20D Breakout": break_20,
        "50D Breakout": break_50,
        "52W Breakout": break_52w,
        "Recent Breakout": bool(recent["match"]),
        "Breakout Date": recent["date"],
        "Breakout Days Ago": int(recent["days_ago"]),
        "Breakout Volume Ratio": round(
            volume_ratio if breakout_today else _number(recent["ratio"]),
            2,
        ),
        "Daily Gain %": round(daily_gain, 2),
        "5D Return %": round(return_5d, 2),
        "Distance To Breakout %": round(distance_to_pivot, 2),
        "Historical Volume Ratio": round(volume_ratio, 2),
        "Breakout Extension %": round(extension, 2),
    }


def select_breakout_trade_setup(metrics: dict[str, Any]) -> dict[str, Any]:
    """Choose between a validated chart pattern and a movement breakout."""
    pattern_match = bool(metrics.get("Any Pattern Match", False))
    pattern_confidence = _number(metrics.get("Pattern Confidence"))
    pattern_pivot = _number(metrics.get("Pattern Pivot Price"))
    movement_match = bool(metrics.get("Movement Scanner Eligible", False))
    movement_score = _number(metrics.get("Breakout Score"))
    movement_pivot = _number(metrics.get("Movement Pivot Price"))

    if movement_match and (
        not pattern_match or movement_score > pattern_confidence
    ):
        return {
            "Primary Pattern": str(metrics.get("Breakout Status", "Momentum")),
            "Pattern Confidence": movement_score,
            "Pattern Pivot Price": movement_pivot,
        }
    return {
        "Primary Pattern": str(metrics.get("Primary Pattern", "Pattern Watch")),
        "Pattern Confidence": pattern_confidence,
        "Pattern Pivot Price": pattern_pivot,
    }


def finalise_breakout_report(report: pd.DataFrame) -> pd.DataFrame:
    frame = report.copy()
    pattern = frame.get(
        "Any Pattern Match",
        pd.Series(False, index=frame.index),
    ).fillna(False).astype(bool)
    movement = frame.get(
        "Movement Scanner Eligible",
        pd.Series(False, index=frame.index),
    ).fillna(False).astype(bool)
    rs = pd.to_numeric(
        frame.get("RS Score", 0),
        errors="coerce",
    ).fillna(0)
    liquidity = frame.get(
        "Liquidity Eligible",
        pd.Series(False, index=frame.index),
    ).fillna(False).astype(bool)

    frame["Breakout Scanner Eligible"] = (
        (pattern | movement)
        & rs.ge(BREAKOUT_MIN_RS_SCORE)
        & liquidity
    )
    frame["Qualified Scanner"] = "Not Qualified"
    frame.loc[pattern & ~movement, "Qualified Scanner"] = "Pattern Breakout"
    frame.loc[movement & ~pattern, "Qualified Scanner"] = "Momentum Movement"
    frame.loc[pattern & movement, "Qualified Scanner"] = (
        "Pattern + Momentum"
    )

    matched = frame.get(
        "Matched Patterns",
        pd.Series("None", index=frame.index),
    ).fillna("None").astype(str)
    matched = matched.str.replace(
        r"(?:,\s*)?Minervini VCP",
        "",
        regex=True,
    ).replace("", "None")
    frame["Matched Patterns"] = matched
    frame["Pattern Count"] = matched.apply(
        lambda value: 0
        if value == "None"
        else len([part for part in value.split(",") if part.strip()])
    )
    frame["Multi-Pattern Confirmation"] = frame["Pattern Count"].ge(2)
    return frame
