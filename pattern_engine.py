from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pandas as pd

from config import (
    BULL_FLAG_ENABLED,
    PATTERN_ENGINE_ENABLED,
)
from patterns.ascending_triangle import detect_ascending_triangle
from patterns.bull_flag import detect_bull_flag
from patterns.cup_handle import detect_cup_with_handle
from patterns.double_bottom import detect_double_bottom
from patterns.episodic_pivot import detect_episodic_pivot
from patterns.flat_base import detect_flat_base
from patterns.high_tight_flag import detect_high_tight_flag
from patterns.ipo_base import detect_ipo_base
from patterns.pocket_pivot_vdu import detect_pocket_pivot_vdu


_ALL_PATTERN_SPECS: tuple[tuple[str, str, Callable[[pd.DataFrame], dict[str, Any]]], ...] = (
    ("Cup with Handle", "Cup Handle", detect_cup_with_handle),
    ("Flat Base", "Flat Base", detect_flat_base),
    ("Double Bottom", "Double Bottom", detect_double_bottom),
    ("Pocket Pivot & VDU", "Pocket Pivot VDU", detect_pocket_pivot_vdu),
    ("Bull Flag", "Bull Flag", detect_bull_flag),
    ("Ascending Triangle", "Ascending Triangle", detect_ascending_triangle),
    ("IPO Base", "IPO Base", detect_ipo_base),
    ("High Tight Flag", "High Tight Flag", detect_high_tight_flag),
    ("Episodic Pivot", "Episodic Pivot", detect_episodic_pivot),
)

PATTERN_SPECS = tuple(
    specification
    for specification in _ALL_PATTERN_SPECS
    if (
        specification[0] != "Bull Flag"
        or BULL_FLAG_ENABLED
    )
)


def analyse_patterns(data: pd.DataFrame) -> dict[str, Any]:
    """Run every V4 detector once against the same completed OHLCV history."""
    if not PATTERN_ENGINE_ENABLED:
        return {}
    result: dict[str, Any] = {}
    for name, prefix, detector in PATTERN_SPECS:
        try:
            result.update(detector(data))
        except Exception as exc:
            logging.debug("%s detector skipped: %s", name, exc)
            result.update(
                {
                    f"{prefix} Match": False,
                    f"{prefix} Mandatory Pass": False,
                    f"{prefix} Confidence": 0.0,
                    f"{prefix} Pivot Price": 0.0,
                    f"{prefix} Reason": f"Detector error: {exc}",
                }
            )
    return result


def select_pattern_trade_setup(metrics: dict[str, Any]) -> dict[str, Any]:
    """Choose one pivot for the shared trade planner and retain every match."""
    matches: list[tuple[str, float, float]] = []
    for name, prefix, _ in PATTERN_SPECS:
        if (
            bool(metrics.get(f"{prefix} Match", False))
            and bool(metrics.get(f"{prefix} Mandatory Pass", False))
        ):
            matches.append(
                (
                    name,
                    _number(metrics.get(f"{prefix} Confidence")),
                    _number(metrics.get(f"{prefix} Pivot Price")),
                )
            )
    usable = [item for item in matches if item[2] > 0]
    usable.sort(key=lambda item: (item[1], item[2]), reverse=True)
    if not usable:
        fallback = _number(metrics.get("Pivot Price"))
        return {
            "Matched Patterns": "None",
            "Pattern Count": 0,
            "Any Pattern Match": False,
            "Primary Pattern": "Minervini Watch",
            "Pattern Confidence": _number(metrics.get("VCP Score")),
            "Pattern Pivot Price": fallback,
        }
    primary = usable[0]
    return {
        "Matched Patterns": ", ".join(item[0] for item in usable),
        "Pattern Count": len(usable),
        "Any Pattern Match": True,
        "Primary Pattern": primary[0],
        "Pattern Confidence": round(primary[1], 1),
        "Pattern Pivot Price": round(primary[2], 2),
    }


def finalise_pattern_columns(report: pd.DataFrame) -> pd.DataFrame:
    """Normalise pattern fields after quality and RS columns are available."""
    frame = report.copy()
    if "Matched Patterns" not in frame:
        frame["Matched Patterns"] = "None"
    if "Pattern Count" not in frame:
        frame["Pattern Count"] = 0
    # Preserve the original Minervini classification when the complete
    # Minervini filter qualifies the stock. Other patterns remain visible
    # as confirmations and may still supply the selected trade-plan pivot.
    minervini_qualified = frame[
        "Trend + RS + Volume + VCP Pass"
    ].fillna(False).astype(bool)

    def add_minervini_confirmation(row: pd.Series) -> str:
        matched = str(row.get("Matched Patterns", "None"))
        if not bool(
            minervini_qualified.loc[row.name]
        ):
            return matched
        parts = [
            part.strip()
            for part in matched.split(",")
            if part.strip() and part.strip() != "None"
        ]
        if "Minervini VCP" not in parts:
            parts.append("Minervini VCP")
        return ", ".join(parts)

    before_minervini = frame["Matched Patterns"].astype(str)
    frame["Matched Patterns"] = frame.apply(
        add_minervini_confirmation,
        axis=1,
    )
    added_minervini = (
        minervini_qualified
        & ~before_minervini.str.contains(
            "Minervini VCP",
            regex=False,
        )
    )
    frame.loc[
        added_minervini,
        "Pattern Count",
    ] = (
        frame.loc[
            added_minervini,
            "Pattern Count",
        ].fillna(0).astype(int)
        + 1
    )
    frame.loc[
        minervini_qualified,
        "Any Pattern Match",
    ] = True

    frame["Multi-Pattern Confirmation"] = (
        frame["Pattern Count"].fillna(0).astype(int) >= 2
    )
    frame["Pattern Agreement Bonus"] = (
        (
            frame["Pattern Count"].fillna(0).astype(float)
            - 1.0
        ).clip(lower=0, upper=3)
        * 2.0
    ).round(1)

    frame["Qualified Scanner"] = "V5 Pattern Engine"
    frame.loc[
        minervini_qualified,
        "Qualified Scanner",
    ] = "Minervini"
    frame.loc[
        minervini_qualified,
        "Primary Pattern",
    ] = "Minervini VCP"
    frame.loc[
        minervini_qualified,
        "Pattern Confidence",
    ] = frame.loc[
        minervini_qualified,
        "VCP Score",
    ].clip(upper=98)
    return frame


def pattern_sheet_specs() -> tuple[tuple[str, str], ...]:
    return tuple((name, f"{prefix} Match") for name, prefix, _ in PATTERN_SPECS)


def _number(value: Any) -> float:
    try:
        number = float(value)
        return 0.0 if pd.isna(number) else number
    except (TypeError, ValueError):
        return 0.0
