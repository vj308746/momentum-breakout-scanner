from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


REQUIRED_OHLCV = ("Open", "High", "Low", "Close", "Volume")


def clean_ohlcv(data: pd.DataFrame, minimum: int = 1) -> pd.DataFrame:
    missing = [column for column in REQUIRED_OHLCV if column not in data.columns]
    if missing:
        raise RuntimeError("Pattern detector missing columns: " + ", ".join(missing))
    frame = data.loc[:, REQUIRED_OHLCV].copy()
    for column in REQUIRED_OHLCV:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=list(REQUIRED_OHLCV))
    if len(frame) < minimum:
        raise RuntimeError(f"Pattern detector requires at least {minimum} records")
    return frame


def pct_change(new: float, old: float) -> float:
    return ((new / old) - 1.0) * 100.0 if old > 0 else 0.0


def depth_pct(high: float, low: float) -> float:
    return ((high - low) / high) * 100.0 if high > 0 else 0.0


def distance_to_pivot(close: float, pivot: float) -> float:
    return ((pivot - close) / pivot) * 100.0 if pivot > 0 else 0.0


def linear_slope_pct(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if len(clean) < 2 or clean[0] == 0:
        return 0.0
    slope = float(np.polyfit(np.arange(len(clean), dtype=float), clean, 1)[0])
    return slope / float(np.mean(clean)) * 100.0


def base_result(prefix: str, reason: str) -> dict[str, Any]:
    return {
        f"{prefix} Match": False,
        f"{prefix} Confidence": 0.0,
        f"{prefix} Pivot Price": 0.0,
        f"{prefix} Reason": reason,
    }


def bounded_score(value: float) -> float:
    # A heuristic chart detector should never present artificial certainty.
    return round(max(0.0, min(98.0, value)), 1)
