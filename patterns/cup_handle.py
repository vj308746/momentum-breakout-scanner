from __future__ import annotations

from typing import Any

import pandas as pd

from config import (
    CUP_LOOKBACK_DAYS,
    CUP_MAX_DEPTH_PCT,
    CUP_MAX_DURATION_DAYS,
    CUP_MIN_CONFIDENCE,
    CUP_MIN_DEPTH_PCT,
    CUP_MIN_DURATION_DAYS,
    CUP_RIGHT_LIP_TOLERANCE_PCT,
    HANDLE_MAX_DAYS,
    HANDLE_MAX_DEPTH_PCT,
    HANDLE_MIN_DAYS,
    HANDLE_VOLUME_DRYUP_RATIO,
)


def detect_cup_with_handle(data: pd.DataFrame) -> dict[str, Any]:
    """Heuristic daily Cup-with-Handle detector.

    It looks for a left lip, rounded/deep middle low, recovery to a
    comparable right lip and a shallow, lower-volume handle near the end.
    The output is deliberately a candidate score, not a guarantee.
    """
    required = {"High", "Low", "Close", "Volume"}
    missing = required.difference(data.columns)
    if missing:
        raise RuntimeError("Cup detector missing: " + ", ".join(sorted(missing)))

    frame = data[["High", "Low", "Close", "Volume"]].dropna().tail(CUP_LOOKBACK_DAYS).copy()
    if len(frame) < CUP_MIN_DURATION_DAYS + HANDLE_MIN_DAYS:
        return _empty("Insufficient history")

    n = len(frame)
    # Leave room for the handle at the end.
    handle_max = min(HANDLE_MAX_DAYS, max(HANDLE_MIN_DAYS, n // 5))
    cup_end_pos = n - HANDLE_MIN_DAYS
    left_zone_end = max(10, int(cup_end_pos * 0.42))
    left_zone = frame.iloc[:left_zone_end]
    left_date = left_zone["High"].idxmax()
    left_pos = frame.index.get_loc(left_date)
    left_lip = float(frame.loc[left_date, "High"])

    # Right lip must occur after a meaningful decline/recovery.
    right_search_start = max(left_pos + 15, int(cup_end_pos * 0.55))
    right_zone = frame.iloc[right_search_start:cup_end_pos]
    if right_zone.empty:
        return _empty("No right-lip region")
    right_date = right_zone["High"].idxmax()
    right_pos = frame.index.get_loc(right_date)
    right_lip = float(frame.loc[right_date, "High"])

    if right_pos - left_pos < CUP_MIN_DURATION_DAYS:
        return _empty("Cup too short")
    if right_pos - left_pos > CUP_MAX_DURATION_DAYS:
        return _empty("Cup too long")

    cup_slice = frame.iloc[left_pos:right_pos + 1]
    trough_date = cup_slice["Low"].idxmin()
    trough_pos = frame.index.get_loc(trough_date)
    trough = float(frame.loc[trough_date, "Low"])
    if trough_pos <= left_pos + 4 or trough_pos >= right_pos - 4:
        return _empty("Trough not centred")

    depth = (left_lip - trough) / left_lip * 100
    lip_difference = abs(right_lip - left_lip) / left_lip * 100

    handle = frame.iloc[right_pos + 1:]
    if len(handle) < HANDLE_MIN_DAYS:
        return _empty("Handle too short")
    if len(handle) > HANDLE_MAX_DAYS:
        handle = handle.tail(HANDLE_MAX_DAYS)

    pivot = max(left_lip, right_lip)
    handle_low = float(handle["Low"].min())
    handle_depth = (right_lip - handle_low) / right_lip * 100
    handle_avg_volume = float(handle["Volume"].mean())
    cup_avg_volume = float(cup_slice["Volume"].mean())
    volume_ratio = handle_avg_volume / cup_avg_volume if cup_avg_volume > 0 else 99.0
    current = float(frame["Close"].iloc[-1])
    distance = (pivot - current) / pivot * 100

    depth_pass = CUP_MIN_DEPTH_PCT <= depth <= CUP_MAX_DEPTH_PCT
    lips_pass = lip_difference <= CUP_RIGHT_LIP_TOLERANCE_PCT
    handle_pass = 0 <= handle_depth <= HANDLE_MAX_DEPTH_PCT
    volume_pass = volume_ratio <= HANDLE_VOLUME_DRYUP_RATIO
    near_pivot = -5.0 <= distance <= 5.0

    depth_midpoint = (
        CUP_MIN_DEPTH_PCT
        + CUP_MAX_DEPTH_PCT
    ) / 2
    depth_quality = (
        15
        + 10
        * max(
            0.0,
            1.0
            - abs(depth - depth_midpoint)
            / max(
                (
                    CUP_MAX_DEPTH_PCT
                    - CUP_MIN_DEPTH_PCT
                )
                / 2,
                1.0,
            ),
        )
        if depth_pass
        else 0
    )
    lips_quality = (
        10
        + 10
        * max(
            0.0,
            1.0
            - lip_difference
            / max(CUP_RIGHT_LIP_TOLERANCE_PCT, 0.01),
        )
        if lips_pass
        else 0
    )
    handle_quality = (
        15
        + 10
        * max(
            0.0,
            1.0
            - handle_depth
            / max(HANDLE_MAX_DEPTH_PCT, 0.01),
        )
        if handle_pass
        else 0
    )
    volume_quality = (
        8
        + 7
        * max(
            0.0,
            (
                HANDLE_VOLUME_DRYUP_RATIO
                - volume_ratio
            )
            / max(HANDLE_VOLUME_DRYUP_RATIO, 0.01),
        )
        if volume_pass
        else 0
    )
    distance_quality = (
        8
        + 7
        * max(
            0.0,
            1.0 - abs(distance) / 5.0,
        )
        if near_pivot
        else 0
    )
    score = (
        depth_quality
        + lips_quality
        + handle_quality
        + volume_quality
        + distance_quality
    )
    score = round(max(0.0, min(98.0, score)), 1)

    matched = bool(
        depth_pass and lips_pass and handle_pass
        and volume_pass and near_pivot
        and len(handle) >= HANDLE_MIN_DAYS
        and score >= CUP_MIN_CONFIDENCE
    )

    return {
        "Cup Handle Match": matched,
        "Cup Handle Mandatory Pass": matched,
        "Cup Handle Confidence": score,
        "Cup Handle Pivot Price": round(pivot, 2),
        "Cup Depth %": round(depth, 2),
        "Cup Duration Days": int(right_pos - left_pos + 1),
        "Cup Lip Difference %": round(lip_difference, 2),
        "Handle Days": int(len(handle)),
        "Handle Depth %": round(handle_depth, 2),
        "Handle Volume Ratio": round(volume_ratio, 2),
        "Cup Distance From Pivot %": round(distance, 2),
        "Cup Handle Reason": _reason(depth_pass, lips_pass, handle_pass, volume_pass, near_pivot),
    }


def _reason(depth: bool, lips: bool, handle: bool, volume: bool, near: bool) -> str:
    parts = []
    parts.append("valid cup depth" if depth else "cup depth outside range")
    parts.append("balanced lips" if lips else "uneven lips")
    parts.append("shallow handle" if handle else "handle too deep")
    parts.append("handle volume dry-up" if volume else "no handle volume dry-up")
    parts.append("near pivot" if near else "not near pivot")
    return ", ".join(parts)


def _empty(reason: str) -> dict[str, Any]:
    return {
        "Cup Handle Match": False,
        "Cup Handle Mandatory Pass": False,
        "Cup Handle Confidence": 0.0,
        "Cup Handle Pivot Price": 0.0,
        "Cup Depth %": 0.0,
        "Cup Duration Days": 0,
        "Cup Lip Difference %": 0.0,
        "Handle Days": 0,
        "Handle Depth %": 0.0,
        "Handle Volume Ratio": 0.0,
        "Cup Distance From Pivot %": 0.0,
        "Cup Handle Reason": reason,
    }
