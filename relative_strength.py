from __future__ import annotations

import pandas as pd

from config import (
    RS_THRESHOLD,
    RS_WEIGHT_3M,
    RS_WEIGHT_6M,
    RS_WEIGHT_12M,
)

TRADING_DAYS_3M = 63
TRADING_DAYS_6M = 126
TRADING_DAYS_12M = 252


def calculate_return(close_prices: pd.Series, trading_days: int) -> float:
    prices = close_prices.dropna()
    if len(prices) <= trading_days:
        return float("nan")

    current = float(prices.iloc[-1])
    previous = float(prices.iloc[-(trading_days + 1)])
    if previous <= 0:
        return float("nan")

    return ((current / previous) - 1) * 100


def calculate_momentum_metrics(data: pd.DataFrame) -> dict[str, float]:
    if "Close" not in data.columns:
        raise RuntimeError("Close column is missing")

    close = data["Close"]
    return {
        "3M Return %": calculate_return(close, TRADING_DAYS_3M),
        "6M Return %": calculate_return(close, TRADING_DAYS_6M),
        "12M Return %": calculate_return(close, TRADING_DAYS_12M),
    }


def add_relative_strength_scores(
    report: pd.DataFrame,
    benchmark_returns: dict[str, float],
) -> pd.DataFrame:
    report = report.copy()

    for column in ("3M Return %", "6M Return %", "12M Return %"):
        report[column] = pd.to_numeric(report[column], errors="coerce")

    report["Nifty 3M Return %"] = benchmark_returns["3M Return %"]
    report["Nifty 6M Return %"] = benchmark_returns["6M Return %"]
    report["Nifty 12M Return %"] = benchmark_returns["12M Return %"]

    report["Relative 3M %"] = (
        report["3M Return %"] - report["Nifty 3M Return %"]
    )
    report["Relative 6M %"] = (
        report["6M Return %"] - report["Nifty 6M Return %"]
    )
    report["Relative 12M %"] = (
        report["12M Return %"] - report["Nifty 12M Return %"]
    )

    for period in ("3M", "6M", "12M"):
        report[f"{period} Percentile"] = (
            report[f"{period} Return %"]
            .rank(method="average", ascending=True, pct=True)
            .mul(100)
        )

    weighted_parts = (
        report["3M Percentile"].fillna(0) * RS_WEIGHT_3M
        + report["6M Percentile"].fillna(0) * RS_WEIGHT_6M
        + report["12M Percentile"].fillna(0) * RS_WEIGHT_12M
    )
    available_weight = (
        report["3M Percentile"].notna().astype(float) * RS_WEIGHT_3M
        + report["6M Percentile"].notna().astype(float) * RS_WEIGHT_6M
        + report["12M Percentile"].notna().astype(float) * RS_WEIGHT_12M
    )
    report["RS Score"] = (
        weighted_parts.div(available_weight.where(available_weight > 0))
        .round(0)
        .clip(1, 100)
    )

    report["RS Pass"] = report["RS Score"] >= RS_THRESHOLD
    report["Trend + RS Pass"] = (
        report["Trend Template Pass"].astype(bool)
        & report["RS Pass"].astype(bool)
    )

    return report
