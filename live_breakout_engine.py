from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class BreakoutState:
    state: str
    resistance: float | None
    breakout_level: float | None
    distance_to_resistance_pct: float | None
    breakout_pct: float | None
    volume_ratio: float | None
    candle_confirmation: bool
    entry: float | None
    stop_loss: float | None
    target_1_2r: float | None
    target_1_3r: float | None
    reason: str


def _num(value: Any) -> float:
    try:
        value = float(value)
        return value if pd.notna(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    rename = {str(c).lower(): c for c in frame.columns}
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(rename):
        raise ValueError("Candles require Open, High, Low, Close and Volume columns.")
    frame = frame.rename(columns={rename[k]: k.title() for k in required})
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).sort_index()


def evaluate_breakout(
    candles: pd.DataFrame,
    *,
    lookback: int = 20,
    near_pct: float = 3.0,
    retest_tolerance_pct: float = 0.75,
    failure_pct: float = 1.0,
    strong_breakout_pct: float = 1.0,
    min_volume_ratio: float = 1.2,
) -> BreakoutState:
    """Evaluate the latest candle using only information available at each candle."""
    frame = _normalise(candles)
    minimum = max(lookback + 5, 30)
    if len(frame) < minimum:
        return BreakoutState("INSUFFICIENT DATA", None, None, None, None, None, False, None, None, None, None, "Not enough candles.")

    high = frame["High"]
    close_series = frame["Close"]
    prior_resistance_series = high.shift(1).rolling(lookback).max()
    breakout_series = close_series > prior_resistance_series * 1.002
    breakout_rows = frame[breakout_series.fillna(False)]
    recent_breakouts = breakout_rows.tail(15)

    latest = frame.iloc[-1]
    close = _num(latest["Close"])
    low = _num(latest["Low"])
    open_price = _num(latest["Open"])
    avg_volume = _num(frame["Volume"].iloc[:-1].tail(20).mean())
    volume_ratio = _num(latest["Volume"]) / avg_volume if avg_volume > 0 else 0.0

    current_resistance = _num(prior_resistance_series.iloc[-1])
    breakout_level = current_resistance
    distance_pct = ((current_resistance - close) / current_resistance * 100) if current_resistance else None
    breakout_pct = ((close - current_resistance) / current_resistance * 100) if current_resistance else None
    candle_confirmation = close > current_resistance and close >= open_price and close > low if current_resistance else False
    state = "BELOW RESISTANCE"
    reason = "Price remains outside the configured breakout zone."

    if not recent_breakouts.empty:
        breakout_index = recent_breakouts.index[-1]
        breakout_position = frame.index.get_loc(breakout_index)
        breakout_level = _num(prior_resistance_series.loc[breakout_index])
        bars_since = len(frame) - 1 - breakout_position
        after = frame.iloc[breakout_position:]
        latest_high = _num(after["High"].max())
        touched = low <= breakout_level * (1 + retest_tolerance_pct / 100)
        held = close >= breakout_level * (1 - retest_tolerance_pct / 100)
        failed = close < breakout_level * (1 - failure_pct / 100)
        strong = close >= breakout_level * (1 + strong_breakout_pct / 100) and volume_ratio >= min_volume_ratio
        if bars_since >= 1 and failed:
            state = "FAILED BREAKOUT"
            reason = "Price closed materially below the most recent breakout level."
        elif bars_since >= 1 and touched and held and close < latest_high * 0.995:
            state = "RETEST HELD"
            reason = "Price revisited the breakout area and remains above the level."
        elif bars_since >= 1 and touched and close <= breakout_level * 1.01:
            state = "RETEST"
            reason = "Price is testing the prior breakout area."
        elif strong:
            state = "STRONG BREAKOUT"
            reason = "Close is above the breakout level with supportive volume."
        elif close > breakout_level:
            state = "CONFIRMED BREAKOUT"
            reason = "Price is holding above the most recent breakout level."
        distance_pct = (breakout_level - close) / breakout_level * 100 if breakout_level else None
        breakout_pct = (close - breakout_level) / breakout_level * 100 if breakout_level else None
        candle_confirmation = close > breakout_level and close >= open_price and close > low
    elif current_resistance:
        if close >= current_resistance:
            state = "TESTING RESISTANCE" if close <= current_resistance * 1.005 else "CONFIRMED BREAKOUT"
            reason = "Price is at/above the current resistance level."
        elif distance_pct is not None and distance_pct <= 1.0:
            state = "TESTING RESISTANCE"
            reason = "Price is within 1% of resistance."
        elif distance_pct is not None and distance_pct <= near_pct:
            state = "NEAR RESISTANCE"
            reason = "Price is within the configured approach zone."

    entry = breakout_level * 1.001 if breakout_level else None
    recent_low = _num(frame["Low"].tail(10).min())
    stop = min(recent_low, breakout_level * 0.99) if breakout_level and recent_low > 0 else None
    if entry and stop and stop >= entry:
        stop = breakout_level * 0.985
    risk = entry - stop if entry and stop else None
    target_1 = entry + 2 * risk if risk and risk > 0 else None
    target_2 = entry + 3 * risk if risk and risk > 0 else None

    return BreakoutState(
        state=state,
        resistance=current_resistance,
        breakout_level=breakout_level,
        distance_to_resistance_pct=distance_pct,
        breakout_pct=breakout_pct,
        volume_ratio=volume_ratio,
        candle_confirmation=candle_confirmation,
        entry=entry,
        stop_loss=stop,
        target_1_2r=target_1,
        target_1_3r=target_2,
        reason=reason,
    )


def state_to_dict(result: BreakoutState) -> dict[str, Any]:
    return {
        "State": result.state,
        "Resistance": result.resistance,
        "Breakout Level": result.breakout_level,
        "Distance To Resistance %": result.distance_to_resistance_pct,
        "Breakout %": result.breakout_pct,
        "Volume Ratio": result.volume_ratio,
        "Candle Confirmation": result.candle_confirmation,
        "Entry": result.entry,
        "Stop Loss": result.stop_loss,
        "Target 1:2R": result.target_1_2r,
        "Target 1:3R": result.target_1_3r,
        "Reason": result.reason,
    }
