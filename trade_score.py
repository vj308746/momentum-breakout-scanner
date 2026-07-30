from __future__ import annotations

from typing import Any

import pandas as pd

from config import (
    BEARISH_MARKET_CONFIDENCE_PENALTY,
    BUY_NOW_MAX_EXTENSION_PCT,
    BUY_ZONE_BELOW_ENTRY_PCT,
    CAUTIOUS_MARKET_CONFIDENCE_PENALTY,
    DECISION_MIN_BUY_SCORE,
    DECISION_MIN_WATCH_SCORE,
    HIGH_RISK_STOP_PCT,
    HOLD_MAX_EXTENSION_PCT,
    LOW_RISK_STOP_PCT,
    MIN_TRADE_SCORE,
    TOP_TRADE_SCORE,
    WATCH_BELOW_ENTRY_PCT,
)


ACTION_PRIORITY = {
    "BUY NOW": 1,
    "WATCH": 2,
    "BUY ON BREAKOUT": 3,
    "BREAKOUT / VOLUME PENDING": 4,
    "WAIT": 5,
    "EXTENDED / DO NOT CHASE": 6,
    "AVOID": 7,
}


def _number(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default

    if pd.isna(result):
        return default

    return result


def _grade(
    score: float,
) -> str:
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 85:
        return "B+"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    return "Reject"


def _market_quality(
    market_status: dict[str, Any],
) -> float:
    status = str(
        market_status.get(
            "Market Status",
            "",
        )
    ).strip().upper()

    if bool(
        market_status.get(
            "Market Bullish",
            False,
        )
    ):
        return 100.0

    if status in {
        "CAUTIOUS",
        "NEUTRAL",
    }:
        return 55.0

    return 30.0


def _risk_level(
    stop_pct: float,
    atr_pct: float,
) -> str:
    if (
        stop_pct <= LOW_RISK_STOP_PCT
        and atr_pct <= 3.0
    ):
        return "LOW"

    if (
        stop_pct >= HIGH_RISK_STOP_PCT
        or atr_pct >= 5.0
    ):
        return "HIGH"

    return "MEDIUM"


def _live_action(
    row: pd.Series,
) -> tuple[
    str,
    str,
    float,
]:
    """
    Return action, entry-window description and live extension.

    Extension is positive when price is above entry and negative
    when price is below entry.
    """

    current = _number(
        row.get("Current Price")
    )
    entry = _number(
        row.get("Suggested Entry")
    )
    score = _number(
        row.get("Trade Quality Score")
    )
    plan_valid = bool(
        row.get(
            "Trade Plan Valid",
            False,
        )
    )
    trend_pass = bool(
        row.get(
            "Trend Template Pass",
            False,
        )
    )

    if entry <= 0:
        return (
            "AVOID",
            "No valid entry",
            0.0,
        )

    extension = (
        (current / entry) - 1
    ) * 100

    if (
        not plan_valid
        or not trend_pass
        or score
        < DECISION_MIN_WATCH_SCORE
    ):
        return (
            "AVOID",
            "Setup quality insufficient",
            extension,
        )

    if extension > HOLD_MAX_EXTENSION_PCT:
        return (
            "EXTENDED / DO NOT CHASE",
            "Fresh entry window expired",
            extension,
        )

    if (
        extension
        > BUY_NOW_MAX_EXTENSION_PCT
    ):
        return (
            "BREAKOUT / VOLUME PENDING",
            "Active only if already owned",
            extension,
        )

    if (
        -BUY_ZONE_BELOW_ENTRY_PCT
        <= extension
        <= BUY_NOW_MAX_EXTENSION_PCT
    ):
        if score >= DECISION_MIN_BUY_SCORE:
            return (
                "BUY NOW",
                "Immediate entry zone",
                extension,
            )

        return (
            "WATCH",
            "At entry but quality below buy threshold",
            extension,
        )

    distance_below = abs(
        min(extension, 0.0)
    )

    if (
        distance_below
        <= WATCH_BELOW_ENTRY_PCT
    ):
        return (
            "WATCH",
            "Close to entry",
            extension,
        )

    return (
        "BUY ON BREAKOUT",
        "Wait for entry trigger",
        extension,
    )


def _confidence_score(
    row: pd.Series,
    market_status: dict[str, Any],
) -> float:
    base = _number(
        row.get(
            "Trade Quality Score"
        )
    )

    current = _number(
        row.get("Current Price")
    )
    entry = _number(
        row.get("Suggested Entry")
    )

    if entry > 0:
        absolute_distance = abs(
            (
                current / entry
                - 1
            )
            * 100
        )
    else:
        absolute_distance = 20.0

    proximity_bonus = max(
        0.0,
        8.0
        - min(
            absolute_distance,
            8.0,
        )
    )

    alignment_bonus = (
        3.0
        if bool(
            row.get(
                "EMA Bullish Alignment",
                False,
            )
        )
        else 0.0
    )

    status = str(
        market_status.get(
            "Market Status",
            "",
        )
    ).strip().upper()

    market_penalty = 0.0

    if status in {
        "CAUTIOUS",
        "NEUTRAL",
    }:
        market_penalty = (
            CAUTIOUS_MARKET_CONFIDENCE_PENALTY
        )
    elif not bool(
        market_status.get(
            "Market Bullish",
            False,
        )
    ):
        market_penalty = (
            BEARISH_MARKET_CONFIDENCE_PENALTY
        )

    return round(
        max(
            0.0,
            min(
                100.0,
                base
                + proximity_bonus
                + alignment_bonus
                - market_penalty,
            ),
        ),
        1,
    )


def _urgency(
    action: str,
    extension: float,
) -> str:
    if action == "BUY NOW":
        return "IMMEDIATE"

    if action == "WATCH":
        return "NEXT 1–2 SESSIONS"

    if action == "BUY ON BREAKOUT":
        return "WAIT FOR TRIGGER"

    if action == "BREAKOUT / VOLUME PENDING":
        return "MANAGE EXISTING POSITION"

    if action == "EXTENDED / DO NOT CHASE":
        return "WAIT FOR NEW BASE"

    return "LOW PRIORITY"


def add_trade_quality_scores(
    report: pd.DataFrame,
    market_status: dict[str, Any],
) -> pd.DataFrame:
    """
    Add quality, confidence, risk and live action fields.

    Breakout-scanner quality weighting:
    - Trend: 15
    - RS: 20
    - Sector: 10
    - Volume: 20
    - Breakout/pattern setup: 25
    - Market: 10
    """

    frame = report.copy()

    trend_component = (
        pd.to_numeric(
            frame["Score %"],
            errors="coerce",
        )
        .fillna(0)
        .clip(0, 100)
        * 0.15
    )

    rs_component = (
        pd.to_numeric(
            frame["RS Score"],
            errors="coerce",
        )
        .fillna(0)
        .clip(0, 100)
        * 0.20
    )

    sector_component = (
        pd.to_numeric(
            frame["Sector RS Score"],
            errors="coerce",
        )
        .fillna(0)
        .clip(0, 100)
        * 0.10
    )

    volume_component = (
        pd.to_numeric(
            frame["Volume Score"],
            errors="coerce",
        )
        .fillna(0)
        .clip(0, 100)
        * 0.20
    )

    setup_score = pd.concat(
        [
            pd.to_numeric(
                frame.get("VCP Score", 0),
                errors="coerce",
            ),
            pd.to_numeric(
                frame.get("Pattern Confidence", 0),
                errors="coerce",
            ),
            pd.to_numeric(
                frame.get("Breakout Score", 0),
                errors="coerce",
            ),
        ],
        axis=1,
    ).fillna(0).max(axis=1).clip(0, 100)
    setup_component = setup_score * 0.25

    market_score = _market_quality(
        market_status
    )

    frame[
        "Market Quality Score"
    ] = market_score

    frame[
        "Trade Quality Score"
    ] = (
        trend_component
        + rs_component
        + sector_component
        + volume_component
        + setup_component
        + market_score * 0.10
    ).round(1)

    frame[
        "Trade Grade"
    ] = frame[
        "Trade Quality Score"
    ].apply(_grade)

    frame[
        "Top Quality Trade"
    ] = (
        frame[
            "Trade Quality Score"
        ]
        >= TOP_TRADE_SCORE
    )

    decisions = frame.apply(
        _live_action,
        axis=1,
        result_type="expand",
    )

    decisions.columns = [
        "Action",
        "Entry Window",
        "Live Extension %",
    ]

    frame[
        decisions.columns
    ] = decisions

    frame[
        "Action Priority"
    ] = (
        frame["Action"]
        .map(ACTION_PRIORITY)
        .fillna(99)
        .astype(int)
    )

    frame[
        "Risk Level"
    ] = frame.apply(
        lambda row: _risk_level(
            _number(
                row.get(
                    "Stop Loss %"
                )
            ),
            _number(
                row.get(
                    "ATR % of Entry"
                )
            ),
        ),
        axis=1,
    )

    frame[
        "Confidence Score"
    ] = frame.apply(
        lambda row: _confidence_score(
            row,
            market_status,
        ),
        axis=1,
    )

    frame[
        "Trade Urgency"
    ] = frame.apply(
        lambda row: _urgency(
            str(row["Action"]),
            _number(
                row.get(
                    "Live Extension %"
                )
            ),
        ),
        axis=1,
    )

    frame[
        "Trade Ready"
    ] = (
        frame["Action"].eq(
            "BUY NOW"
        )
        & (
            frame[
                "Trade Quality Score"
            ]
            >= MIN_TRADE_SCORE
        )
    )

    frame[
        "Why Selected"
    ] = frame.apply(
        _selection_reason,
        axis=1,
    )

    frame[
        "Decision Reason"
    ] = frame.apply(
        _decision_reason,
        axis=1,
    )

    return frame


def _selection_reason(
    row: pd.Series,
) -> str:
    reasons: list[str] = []

    if bool(
        row.get(
            "Trend Template Pass",
            False,
        )
    ):
        reasons.append(
            "trend template passed"
        )

    if _number(
        row.get("RS Score")
    ) >= 80:
        reasons.append(
            "strong relative strength"
        )

    if _number(
        row.get(
            "Sector RS Score"
        )
    ) >= 80:
        reasons.append(
            "leading sector"
        )

    if _number(
        row.get("Volume Score")
    ) >= 80:
        reasons.append(
            "strong volume profile"
        )

    if _number(
        row.get("VCP Score")
    ) >= 80:
        reasons.append(
            "high-quality VCP"
        )

    if bool(
        row.get(
            "EMA Bullish Alignment",
            False,
        )
    ):
        reasons.append(
            "10 EMA > 20 EMA > 50 EMA"
        )

    if bool(
        row.get(
            "Ready Near Pivot",
            False,
        )
    ):
        reasons.append(
            "near pivot"
        )

    if bool(
        row.get(
            "Qualified Breakout",
            False,
        )
    ):
        reasons.append(
            "qualified breakout"
        )

    return (
        ", ".join(reasons)
        if reasons
        else "No strong selection factors."
    )


def _decision_reason(
    row: pd.Series,
) -> str:
    action = str(
        row.get(
            "Action",
            "AVOID",
        )
    )

    extension = _number(
        row.get(
            "Live Extension %"
        )
    )

    if action == "BUY NOW":
        return (
            "Live price is in the permitted entry zone "
            "and the quality threshold is met."
        )

    if action == "WATCH":
        return (
            "Price is close to the entry; wait for confirmation "
            "and acceptable volume."
        )

    if action == "BUY ON BREAKOUT":
        return (
            f"Price remains {abs(extension):.2f}% below entry; "
            "buy only after the trigger."
        )

    if action == "BREAKOUT / VOLUME PENDING":
        return (
            f"Price is {extension:.2f}% above entry. "
            "Hold only if already owned; do not add a fresh position."
        )

    if action == "EXTENDED / DO NOT CHASE":
        return (
            f"Price is {extension:.2f}% above entry. "
            "The fresh entry window has expired."
        )

    return (
        "Setup quality, trend or risk does not meet "
        "the minimum decision rules."
    )
