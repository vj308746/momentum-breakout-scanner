from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from config import (
    MAX_PIVOT_EXTENSION_PCT,
    NEAR_PIVOT_THRESHOLD_PCT,
    PIVOT_LOOKBACK_DAYS,
    VCP_LOOKBACK_DAYS,
    VCP_MAX_BASE_DEPTH_PCT,
    VCP_MIN_CONTRACTIONS,
    VCP_SCORE_THRESHOLD,
    VCP_SWING_WINDOW,
)


def find_swing_points(
    data: pd.DataFrame,
    window: int,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    swing_highs: list[tuple[int, float]] = []
    swing_lows: list[tuple[int, float]] = []
    highs = data["High"].to_numpy(dtype=float)
    lows = data["Low"].to_numpy(dtype=float)

    for index in range(window, len(data) - window):
        high_slice = highs[index - window:index + window + 1]
        low_slice = lows[index - window:index + window + 1]

        if highs[index] == np.max(high_slice):
            swing_highs.append((index, float(highs[index])))
        if lows[index] == np.min(low_slice):
            swing_lows.append((index, float(lows[index])))

    return swing_highs, swing_lows


def calculate_pullbacks(
    swing_highs: list[tuple[int, float]],
    swing_lows: list[tuple[int, float]],
) -> list[dict[str, float | int]]:
    contractions: list[dict[str, float | int]] = []

    for high_index, high_price in swing_highs:
        later_lows = [
            (low_index, low_price)
            for low_index, low_price in swing_lows
            if low_index > high_index
        ]
        if not later_lows or high_price <= 0:
            continue

        low_index, low_price = later_lows[0]
        intervening_high = any(
            high_index < index < low_index
            for index, _ in swing_highs
        )
        if intervening_high:
            continue

        pullback = ((high_price - low_price) / high_price) * 100
        if pullback > 0:
            contractions.append(
                {
                    "high_index": high_index,
                    "low_index": low_index,
                    "pullback_pct": pullback,
                }
            )

    unique: list[dict[str, float | int]] = []
    used_lows: set[int] = set()
    for item in contractions:
        low_index = int(item["low_index"])
        if low_index not in used_lows:
            unique.append(item)
            used_lows.add(low_index)

    return unique


def calculate_vcp_metrics(data: pd.DataFrame) -> dict[str, Any]:
    recent = (
        data[["Close", "High", "Low", "Volume"]]
        .dropna()
        .tail(VCP_LOOKBACK_DAYS)
        .reset_index(drop=True)
    )

    minimum = max(50, PIVOT_LOOKBACK_DAYS + 2)
    if len(data.dropna()) < minimum:
        raise RuntimeError(f"At least {minimum} records are required for VCP")

    swing_highs, swing_lows = find_swing_points(recent, VCP_SWING_WINDOW)
    contractions = calculate_pullbacks(swing_highs, swing_lows)[-3:]
    pullbacks = [round(float(item["pullback_pct"]), 2) for item in contractions]

    tightening = (
        len(pullbacks) >= VCP_MIN_CONTRACTIONS
        and all(current < previous for previous, current in zip(pullbacks, pullbacks[1:]))
    )

    base_high = float(recent["High"].max())
    base_low = float(recent["Low"].min())
    base_depth = ((base_high - base_low) / base_high) * 100

    range_50 = float(recent.tail(50)["High"].max() - recent.tail(50)["Low"].min())
    range_10 = float(recent.tail(10)["High"].max() - recent.tail(10)["Low"].min())
    range_ratio = range_10 / range_50 if range_50 > 0 else float("nan")

    clean = data[["Close", "High"]].dropna()
    current_price = float(clean["Close"].iloc[-1])
    pivot_price = float(
        clean.iloc[-(PIVOT_LOOKBACK_DAYS + 1):-1]["High"].max()
    )

    distance = ((pivot_price - current_price) / pivot_price) * 100
    extension = ((current_price - pivot_price) / pivot_price) * 100
    near_pivot = 0 <= distance <= NEAR_PIVOT_THRESHOLD_PCT
    breakout = current_price > pivot_price
    breakout_not_extended = breakout and extension <= MAX_PIVOT_EXTENSION_PCT

    score = 0.0
    score += 30 if len(pullbacks) >= 4 else 25 if len(pullbacks) == 3 else 15 if len(pullbacks) == 2 else 0
    if tightening:
        score += 30
    score += 20 if base_depth <= 15 else 15 if base_depth <= 25 else 10 if base_depth <= VCP_MAX_BASE_DEPTH_PCT else 0
    if not pd.isna(range_ratio):
        score += 20 if range_ratio <= 0.30 else 15 if range_ratio <= 0.45 else 10 if range_ratio <= 0.60 else 0
    score = round(min(score, 100), 2)

    vcp_pass = (
        len(pullbacks) >= VCP_MIN_CONTRACTIONS
        and tightening
        and base_depth <= VCP_MAX_BASE_DEPTH_PCT
        and score >= VCP_SCORE_THRESHOLD
    )

    padded = pullbacks + [float("nan")] * (3 - len(pullbacks))
    return {
        "Swing High Count": len(swing_highs),
        "Swing Low Count": len(swing_lows),
        "Contraction Count": len(pullbacks),
        "Contraction 1 %": padded[0],
        "Contraction 2 %": padded[1],
        "Contraction 3 %": padded[2],
        "Contraction Sequence": " → ".join(f"{value:.2f}%" for value in pullbacks),
        "Contractions Tightening": tightening,
        "Base Depth %": round(base_depth, 2),
        "Base Depth Pass": base_depth <= VCP_MAX_BASE_DEPTH_PCT,
        "10D vs 50D Range Ratio": round(range_ratio, 2),
        "VCP Score": score,
        "VCP Pass": vcp_pass,
        "Pivot Price": round(pivot_price, 2),
        "Distance From Pivot %": round(distance, 2),
        "Pivot Extension %": round(extension, 2),
        "Near Pivot": near_pivot,
        "Pivot Breakout": breakout,
        "Breakout Not Extended": breakout_not_extended,
    }


def add_vcp_combined_flags(report: pd.DataFrame) -> pd.DataFrame:
    report = report.copy()

    report["Trend + RS + Volume + VCP Pass"] = (
        report["Trend Template Pass"].astype(bool)
        & report["RS Pass"].astype(bool)
        & report["Volume Setup Pass"].astype(bool)
        & report["VCP Pass"].astype(bool)
    )

    report["Ready Near Pivot"] = (
        report["Trend + RS + Volume + VCP Pass"]
        & report["Near Pivot"].astype(bool)
    )

    report["Qualified Breakout"] = (
        report["Trend Template Pass"].astype(bool)
        & report["RS Pass"].astype(bool)
        & report["VCP Pass"].astype(bool)
        & report["Pivot Breakout"].astype(bool)
        & report["Breakout Not Extended"].astype(bool)
        & report["Breakout Volume Pass"].astype(bool)
    )

    return report
