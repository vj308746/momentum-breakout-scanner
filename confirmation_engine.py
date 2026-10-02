from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ConfirmationResult:
    score: float
    status: str
    components: dict[str, float]
    reasons: list[str]


def _num(value: Any) -> float | None:
    try:
        v = float(value)
        return v if pd.notna(v) else None
    except (TypeError, ValueError):
        return None


def confirm(row: pd.Series) -> ConfirmationResult:
    """Apply an intraday confirmation layer on top of the existing engine.

    This is intentionally additive: it does not alter the project's existing
    pattern engine or breakout state. It combines live price/volume evidence
    with the daily scanner metadata when available.
    """
    components: dict[str, float] = {}
    reasons: list[str] = []

    state = str(row.get("State", ""))
    state_points = {
        "STRONG BREAKOUT": 25, "CONFIRMED BREAKOUT": 22, "RETEST HELD": 24,
        "RETEST": 15, "TESTING RESISTANCE": 10, "NEAR RESISTANCE": 6,
        "BELOW RESISTANCE": 0, "FAILED BREAKOUT": 0,
    }
    components["Breakout State"] = float(state_points.get(state, 0))
    if components["Breakout State"] >= 20:
        reasons.append("live breakout state is confirmed")

    volume = _num(row.get("Volume Ratio")) or 0.0
    components["Volume"] = min(20.0, max(0.0, volume / 2.0 * 20.0))
    if volume >= 1.5:
        reasons.append(f"volume expansion {volume:.2f}x")

    components["Candle"] = 15.0 if bool(row.get("Candle Confirmation", False)) else 0.0
    if components["Candle"]:
        reasons.append("candle confirmation passed")

    rs = _num(row.get("RS Score"))
    components["Relative Strength"] = min(15.0, max(0.0, (rs or 0.0) / 100.0 * 15.0))
    if rs is not None and rs >= 70:
        reasons.append(f"RS score {rs:.0f}")

    trend = row.get("Trend Template Pass")
    components["Trend"] = 15.0 if str(trend).lower() in {"true", "1", "yes"} or trend is True else 0.0
    if components["Trend"]:
        reasons.append("trend template passed")

    extension = _num(row.get("Breakout %"))
    if extension is None:
        extension = 0.0
    components["Extension"] = 10.0 if extension <= 5.0 else max(0.0, 10.0 - (extension - 5.0) * 2.0)
    if extension > 5.0:
        reasons.append(f"extension {extension:.2f}% requires caution")

    score = round(sum(components.values()), 1)
    if state == "FAILED BREAKOUT":
        status = "FAILED"
    elif score >= 75:
        status = "CONFIRMED"
    elif score >= 55:
        status = "WATCH"
    else:
        status = "EARLY"
    if not reasons:
        reasons.append("insufficient confirmation evidence")
    return ConfirmationResult(score, status, components, reasons)


def enrich(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    out = frame.copy()
    results = out.apply(confirm, axis=1)
    out["Confirmation Score"] = [r.score for r in results]
    out["Confirmation Status"] = [r.status for r in results]
    out["Confirmation Reason"] = ["; ".join(r.reasons) for r in results]
    return out
