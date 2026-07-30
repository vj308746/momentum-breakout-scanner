from __future__ import annotations

import pandas as pd

from config import (
    BREAKOUT_VOLUME_THRESHOLD,
    UP_DOWN_VOLUME_THRESHOLD,
    VOLUME_DRY_UP_THRESHOLD,
    VOLUME_SCORE_THRESHOLD,
)


def safe_divide(numerator: float, denominator: float) -> float:
    if pd.isna(denominator) or denominator <= 0:
        return float("nan")
    return numerator / denominator


def calculate_volume_metrics(data: pd.DataFrame) -> dict[str, float | bool]:
    clean = data[["Close", "Volume"]].dropna().copy()
    if len(clean) < 60:
        raise RuntimeError("At least 60 records are required for volume analysis")

    latest_volume = float(clean["Volume"].iloc[-1])
    avg_10 = float(clean["Volume"].tail(10).mean())
    avg_20 = float(clean["Volume"].tail(20).mean())
    avg_50 = float(clean["Volume"].tail(50).mean())
    previous_40 = float(clean["Volume"].iloc[-50:-10].mean())

    dry_up_ratio = safe_divide(avg_10, previous_40)
    current_ratio = safe_divide(latest_volume, avg_20)
    avg_20_vs_50 = safe_divide(avg_20, avg_50)

    clean["Price Change"] = clean["Close"].diff()
    last_50 = clean.tail(50)
    up_volume = float(
        last_50.loc[last_50["Price Change"] > 0, "Volume"].sum()
    )
    down_volume = float(
        last_50.loc[last_50["Price Change"] < 0, "Volume"].sum()
    )
    up_down_ratio = safe_divide(up_volume, down_volume)

    dry_up_pass = (
        not pd.isna(dry_up_ratio)
        and dry_up_ratio <= VOLUME_DRY_UP_THRESHOLD
    )
    avg_pass = not pd.isna(avg_20_vs_50) and avg_20_vs_50 < 1
    up_down_pass = (
        not pd.isna(up_down_ratio)
        and up_down_ratio >= UP_DOWN_VOLUME_THRESHOLD
    )
    breakout_volume_pass = (
        not pd.isna(current_ratio)
        and current_ratio >= BREAKOUT_VOLUME_THRESHOLD
    )

    score = 0.0
    if not pd.isna(dry_up_ratio):
        score += 50 if dry_up_ratio <= 0.60 else 40 if dry_up_ratio <= 0.75 else 25 if dry_up_ratio <= 0.90 else 10 if dry_up_ratio <= 1.00 else 0
    if avg_pass:
        score += 20
    if not pd.isna(up_down_ratio):
        score += 30 if up_down_ratio >= 1.50 else 25 if up_down_ratio >= 1.20 else 20 if up_down_ratio >= 1.00 else 10 if up_down_ratio >= 0.80 else 0

    score = round(min(score, 100), 2)

    return {
        "Current Volume": round(latest_volume, 0),
        "10D Avg Volume": round(avg_10, 0),
        "20D Avg Volume": round(avg_20, 0),
        "50D Avg Volume": round(avg_50, 0),
        "Volume Dry-Up Ratio": round(dry_up_ratio, 2),
        "20D vs 50D Volume Ratio": round(avg_20_vs_50, 2),
        "Current Volume Ratio": round(current_ratio, 2),
        "Up/Down Volume Ratio": round(up_down_ratio, 2),
        "Volume Dry-Up Pass": dry_up_pass,
        "20D Volume < 50D Volume": avg_pass,
        "Up/Down Volume Pass": up_down_pass,
        "Breakout Volume Pass": breakout_volume_pass,
        "Volume Score": score,
        "Volume Setup Pass": score >= VOLUME_SCORE_THRESHOLD,
    }


def add_combined_volume_flags(report: pd.DataFrame) -> pd.DataFrame:
    report = report.copy()
    report["Trend + RS + Volume Pass"] = (
        report["Trend Template Pass"].astype(bool)
        & report["RS Pass"].astype(bool)
        & report["Volume Setup Pass"].astype(bool)
    )
    return report
