from __future__ import annotations

"""Minervini-inspired swing setup detection.

This module is deliberately setup-oriented: it does not call every stock near
support a buy. It first requires a constructive trend, then scores support
quality, distance to support, price/volume behaviour and proximity to a pivot.
"""

import numpy as np
import pandas as pd

from config import (
    SWING_LOOKBACK_DAYS,
    SWING_SUPPORT_ZONE_PCT,
    SWING_NEAR_SUPPORT_PCT,
    SWING_NEAR_PIVOT_PCT,
    SWING_MIN_SCORE,
    SWING_MIN_TREND_SCORE,
    SWING_MAX_BASE_DEPTH_PCT,
)


def _series(data: pd.DataFrame, name: str) -> pd.Series:
    return pd.to_numeric(data[name], errors="coerce") if name in data else pd.Series(np.nan, index=data.index)


def _cluster_levels(levels: list[float], zone_pct: float) -> list[tuple[float, float, int]]:
    if not levels:
        return []
    levels = sorted(float(x) for x in levels if np.isfinite(x) and x > 0)
    clusters: list[list[float]] = []
    for level in levels:
        if not clusters:
            clusters.append([level])
            continue
        center = float(np.mean(clusters[-1]))
        if abs(level - center) / center * 100 <= zone_pct:
            clusters[-1].append(level)
        else:
            clusters.append([level])
    return [(float(min(c)), float(max(c)), len(c)) for c in clusters]


def calculate_swing_setup_metrics(data: pd.DataFrame) -> dict[str, object]:
    if data is None or data.empty or len(data) < 60:
        return {
            "Swing Setup Status": "INSUFFICIENT DATA",
            "Swing Setup Score": 0.0,
            "Swing Trend Score": 0.0,
            "Support Score": 0.0,
            "Support Price": np.nan,
            "Support Zone Low": np.nan,
            "Support Zone High": np.nan,
            "Support Distance %": np.nan,
            "Pivot Resistance": np.nan,
            "Pivot Distance %": np.nan,
            "Support Touches": 0,
            "Support Source": "UNAVAILABLE",
            "Constructive Volume": False,
            "Support Price Behaviour": "UNAVAILABLE",
            "Swing Setup Pass": False,
        }

    df = data.copy()
    close = _series(df, "Close")
    high = _series(df, "High")
    low = _series(df, "Low")
    volume = _series(df, "Volume")
    current = float(close.iloc[-1])
    if not np.isfinite(current) or current <= 0:
        return {"Swing Setup Status": "INVALID PRICE", "Swing Setup Score": 0.0, "Swing Setup Pass": False}

    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    avg20vol = volume.rolling(20).mean()

    trend_parts = [
        current > float(sma20.iloc[-1]) if np.isfinite(sma20.iloc[-1]) else False,
        current > float(sma50.iloc[-1]) if np.isfinite(sma50.iloc[-1]) else False,
        current > float(sma200.iloc[-1]) if np.isfinite(sma200.iloc[-1]) else False,
        float(sma50.iloc[-1]) > float(sma200.iloc[-1]) if np.isfinite(sma50.iloc[-1]) and np.isfinite(sma200.iloc[-1]) else False,
        float(sma200.iloc[-1]) > float(sma200.iloc[-21]) if len(sma200) > 21 and np.isfinite(sma200.iloc[-21]) else False,
    ]
    swing_trend_score = sum(trend_parts) / len(trend_parts) * 100

    lookback = df.tail(min(SWING_LOOKBACK_DAYS, len(df))).copy()
    l = low.tail(len(lookback)).reset_index(drop=True)
    h = high.tail(len(lookback)).reset_index(drop=True)
    c = close.tail(len(lookback)).reset_index(drop=True)

    # Local pivot lows: a low that is lower than a small neighbourhood.
    window = 3
    support_levels: list[float] = []
    for i in range(window, len(l) - window):
        value = float(l.iloc[i])
        if not np.isfinite(value):
            continue
        neighbourhood = pd.concat([l.iloc[i-window:i], l.iloc[i+1:i+window+1]])
        if value <= float(neighbourhood.min()) * 1.003:
            support_levels.append(value)

    # Moving averages are dynamic support candidates.
    for ma in (sma20.iloc[-1], sma50.iloc[-1], sma200.iloc[-1]):
        if np.isfinite(ma):
            support_levels.append(float(ma))

    clusters = _cluster_levels(support_levels, SWING_SUPPORT_ZONE_PCT)
    near_clusters = [z for z in clusters if z[1] <= current * (1 + SWING_NEAR_SUPPORT_PCT / 100) and z[0] >= current * (1 - SWING_NEAR_SUPPORT_PCT / 100)]
    if not near_clusters:
        near_clusters = sorted(clusters, key=lambda z: abs(current - np.mean(z[:2])))[:3]

    support_low = support_high = support = np.nan
    touches = 0
    source = "NONE"
    if near_clusters:
        best = min(near_clusters, key=lambda z: abs(current - np.mean(z[:2])))
        support_low, support_high, touches = best
        support = float(np.mean(best[:2]))
        source = "SWING LOWS / MOVING AVERAGE"

    support_distance = ((current - support) / support * 100) if np.isfinite(support) else np.nan

    # Pivot/resistance: highest prior high over the recent base window, excluding today.
    prior_highs = high.tail(min(60, len(high))).iloc[:-1]
    pivot = float(prior_highs.max()) if not prior_highs.empty else np.nan
    pivot_distance = ((pivot - current) / current * 100) if np.isfinite(pivot) else np.nan

    # Constructive behaviour: avoid treating a large red/high-volume bar at support as bullish.
    last_open = float(_series(df, "Open").iloc[-1]) if "Open" in df else np.nan
    last_high = float(high.iloc[-1])
    last_low = float(low.iloc[-1])
    last_vol = float(volume.iloc[-1]) if np.isfinite(volume.iloc[-1]) else np.nan
    vol_ratio = last_vol / float(avg20vol.iloc[-1]) if np.isfinite(last_vol) and np.isfinite(avg20vol.iloc[-1]) and avg20vol.iloc[-1] > 0 else np.nan
    close_location = (current - last_low) / (last_high - last_low) if last_high > last_low else 0.5
    daily_return = (current / float(close.iloc[-2]) - 1) * 100 if len(close) > 1 and np.isfinite(close.iloc[-2]) else 0
    red_heavy = np.isfinite(last_open) and current < last_open and close_location < 0.45
    constructive_volume = bool(not red_heavy and (close_location >= 0.55 or daily_return >= 0) and (not np.isfinite(vol_ratio) or vol_ratio <= 2.5))

    distance_score = 100.0 if np.isfinite(support_distance) and 0 <= support_distance <= 1 else max(0.0, 100 - abs(support_distance) * 20) if np.isfinite(support_distance) else 0.0
    touch_score = min(100.0, touches * 30.0)
    support_score = min(100.0, touch_score * 0.55 + distance_score * 0.45)
    volume_score = 100.0 if constructive_volume else 25.0
    pivot_score = 100.0 if np.isfinite(pivot_distance) and 0 <= pivot_distance <= SWING_NEAR_PIVOT_PCT else max(0.0, 100 - max(0.0, pivot_distance) * 15) if np.isfinite(pivot_distance) else 0

    score = round(
        swing_trend_score * 0.30
        + support_score * 0.30
        + distance_score * 0.20
        + volume_score * 0.10
        + pivot_score * 0.10,
        1,
    )

    near_support = np.isfinite(support_distance) and -0.5 <= support_distance <= SWING_NEAR_SUPPORT_PCT
    near_pivot = np.isfinite(pivot_distance) and 0 <= pivot_distance <= SWING_NEAR_PIVOT_PCT
    trend_ok = swing_trend_score >= SWING_MIN_TREND_SCORE
    setup_pass = bool(trend_ok and constructive_volume and score >= SWING_MIN_SCORE and (near_support or near_pivot))

    if setup_pass and near_pivot and not near_support:
        status = "NEAR PIVOT"
    elif setup_pass and near_support:
        status = "NEAR SUPPORT"
    elif trend_ok and (near_support or near_pivot):
        status = "WATCH"
    else:
        status = "NO SETUP"

    return {
        "Swing Setup Status": status,
        "Swing Setup Score": score,
        "Swing Trend Score": round(swing_trend_score, 1),
        "Support Score": round(support_score, 1),
        "Support Price": support,
        "Support Zone Low": support_low,
        "Support Zone High": support_high,
        "Support Distance %": round(support_distance, 2) if np.isfinite(support_distance) else np.nan,
        "Pivot Resistance": pivot,
        "Pivot Distance %": round(pivot_distance, 2) if np.isfinite(pivot_distance) else np.nan,
        "Support Touches": int(touches),
        "Support Source": source,
        "Constructive Volume": constructive_volume,
        "Swing Volume Ratio": round(vol_ratio, 2) if np.isfinite(vol_ratio) else np.nan,
        "Support Price Behaviour": "CONSTRUCTIVE" if constructive_volume else "SELLING PRESSURE",
        "Near Swing Support": bool(near_support),
        "Near Swing Pivot": bool(near_pivot),
        "Swing Setup Pass": setup_pass,
    }


def add_swing_setup_metrics(report: pd.DataFrame, data_by_symbol: dict[str, pd.DataFrame]) -> pd.DataFrame:
    enriched = []
    for _, row in report.iterrows():
        symbol = str(row.get("Symbol", "")).strip()
        metrics = calculate_swing_setup_metrics(data_by_symbol.get(symbol, pd.DataFrame()))
        enriched.append(metrics)
    metrics_df = pd.DataFrame(enriched, index=report.index)
    for col in metrics_df.columns:
        report[col] = metrics_df[col]
    report["Swing Setup Qualified"] = report["Swing Setup Pass"].astype(bool) & report.get("Liquidity Eligible", True).astype(bool)
    return report
