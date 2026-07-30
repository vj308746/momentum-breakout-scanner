from __future__ import annotations

import math
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from config import (
    ACCOUNT_CAPITAL,
    BEARISH_MARKET_CONFIDENCE_PENALTY,
    CAUTIOUS_MARKET_CONFIDENCE_PENALTY,
    CIRCUIT_GUARD_ENABLED,
    CONFIDENCE_WEIGHT_PROXIMITY,
    CONFIDENCE_WEIGHT_QUALITY,
    CONFIDENCE_WEIGHT_RS,
    CONFIDENCE_WEIGHT_SECTOR,
    CONFIDENCE_WEIGHT_VCP,
    CONFIDENCE_WEIGHT_VOLUME,
    HIGH_RISK_STOP_PCT,
    LIVE_BUY_REQUIRES_VOLUME,
    LIVE_NEAR_TRIGGER_PCT,
    LIVE_VOLUME_ACCEPTABLE_RATIO,
    LIVE_VOLUME_CONFIRMATION_ENABLED,
    LIVE_VOLUME_GOOD_RATIO,
    LIVE_VOLUME_MIN_ELAPSED_MINUTES,
    LIVE_VOLUME_STRONG_RATIO,
    LIVE_WAIT_MAX_BELOW_ENTRY_PCT,
    LIVE_WATCH_BELOW_ENTRY_PCT,
    LOW_RISK_STOP_PCT,
    MARKET_CLOSE_HOUR,
    MARKET_CLOSE_MINUTE,
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    MARKET_SESSION_MINUTES,
    MAX_ALLOWED_EXTENSION_PCT,
    MAX_BUY_EXTENSION_PCT,
    MIN_BUY_CONFIDENCE,
    MIN_WATCH_CONFIDENCE,
    RISK_PER_TRADE_PCT,
    UPPER_CIRCUIT_BLOCK_DISTANCE_PCT,
    UPPER_CIRCUIT_CAUTION_DISTANCE_PCT,
)


ACTION_PRIORITY = {
    "BUY NOW": 6,
    "NEAR TRIGGER": 5,
    "WATCH": 4,
    "WAIT": 3,
    "BREAKOUT / VOLUME PENDING": 2,
    "EXTENDED / DO NOT CHASE": 1,
    "AVOID": 0,
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


def _circuit_metrics(
    row: pd.Series,
    current: float,
    entry: float,
) -> dict[str, Any]:
    """Evaluate whether today's upper circuit makes entry impractical."""
    upper = _number(
        row.get("Upper Circuit", 0)
    )
    lower = _number(
        row.get("Lower Circuit", 0)
    )
    sell_quantity_value = row.get(
        "Total Sell Quantity",
        None,
    )
    sell_quantity = (
        _number(sell_quantity_value)
        if sell_quantity_value is not None
        else None
    )

    if (
        not CIRCUIT_GUARD_ENABLED
        or upper <= 0
        or current <= 0
    ):
        return {
            "Circuit Data Available": False,
            "Upper Circuit": upper or None,
            "Lower Circuit": lower or None,
            "Distance To Upper Circuit %": None,
            "Entry Above Upper Circuit": False,
            "Near Upper Circuit": False,
            "Upper Circuit Blocked": False,
            "Circuit Execution Status": "UNAVAILABLE",
            "Circuit Execution Note": (
                "Circuit-limit data unavailable; confirm in broker."
            ),
        }

    distance = max(
        0.0,
        (upper - current) / upper * 100,
    )
    entry_above_upper = entry > upper
    blocked = (
        current >= upper
        or distance
        <= UPPER_CIRCUIT_BLOCK_DISTANCE_PCT
    )
    caution = (
        not blocked
        and distance
        <= UPPER_CIRCUIT_CAUTION_DISTANCE_PCT
    )

    if entry_above_upper:
        status = "ENTRY UNREACHABLE TODAY"
        note = (
            f"Planned entry ₹{entry:.2f} is above today's "
            f"upper circuit ₹{upper:.2f}."
        )
    elif blocked:
        status = "UPPER CIRCUIT BLOCK"
        note = (
            f"Price is only {distance:.2f}% below today's "
            "upper circuit; a fresh order may not fill."
        )
    elif caution:
        status = "UPPER CIRCUIT CAUTION"
        note = (
            f"Price is {distance:.2f}% below today's upper "
            "circuit; verify sell-side liquidity before entry."
        )
    else:
        status = "CLEAR"
        note = (
            f"Price is {distance:.2f}% below today's "
            "upper circuit."
        )

    return {
        "Circuit Data Available": True,
        "Upper Circuit": round(upper, 2),
        "Lower Circuit": (
            round(lower, 2)
            if lower > 0
            else None
        ),
        "Distance To Upper Circuit %": round(
            distance,
            2,
        ),
        "Entry Above Upper Circuit": entry_above_upper,
        "Near Upper Circuit": blocked or caution,
        "Upper Circuit Blocked": blocked,
        "Circuit Execution Status": status,
        "Circuit Execution Note": note,
        "Circuit Sell Quantity": sell_quantity,
    }


def _market_session() -> tuple[
    str,
    int,
]:
    """
    Return session mode and elapsed market minutes in IST.

    Modes:
      PRE_OPEN, LIVE, CLOSED, NON_TRADING_DAY
    """

    now = datetime.now(
        ZoneInfo("Asia/Kolkata")
    )

    if now.weekday() >= 5:
        return (
            "NON_TRADING_DAY",
            0,
        )

    market_open = now.replace(
        hour=MARKET_OPEN_HOUR,
        minute=MARKET_OPEN_MINUTE,
        second=0,
        microsecond=0,
    )

    market_close = now.replace(
        hour=MARKET_CLOSE_HOUR,
        minute=MARKET_CLOSE_MINUTE,
        second=0,
        microsecond=0,
    )

    if now < market_open:
        return (
            "PRE_OPEN",
            0,
        )

    if now <= market_close:
        elapsed = int(
            (
                now - market_open
            ).total_seconds()
            // 60
        )
        return (
            "LIVE",
            max(
                0,
                min(
                    elapsed,
                    MARKET_SESSION_MINUTES,
                ),
            ),
        )

    return (
        "CLOSED",
        MARKET_SESSION_MINUTES,
    )


def _volume_metrics(
    row: pd.Series,
) -> dict[str, Any]:
    """
    Build a transparent volume-confirmation signal.

    The output includes the raw values used in the calculation so the
    Telegram report can show exactly why the ratio is classified as
    STRONG, GOOD, ACCEPTABLE, WEAK or PENDING.

    During a live trading session:
        projected full-session volume
        = current cumulative volume / elapsed minutes * 375

    On a closed market, weekend, holiday or pre-open run:
        latest completed/current daily volume
        = Current Volume when available, otherwise LTP Volume Today
    """

    mode, elapsed_minutes = _market_session()

    average_volume = _number(
        row.get(
            "20D Avg Volume",
            0,
        )
    )

    ltp_volume_today = _number(
        row.get(
            "LTP Volume Today",
            0,
        )
    )

    current_volume = _number(
        row.get(
            "Current Volume",
            0,
        )
    )

    completed_ratio = _number(
        row.get(
            "Current Volume Ratio",
            0,
        )
    )

    ratio = 0.0
    ratio_source = "UNAVAILABLE"
    status = "PENDING"
    confirmed = False
    note = "Volume confirmation is unavailable."
    projected_volume = 0.0
    volume_used = 0.0
    calculation_text = "Volume data unavailable."

    if not LIVE_VOLUME_CONFIRMATION_ENABLED:
        return {
            "Volume Confirmation": "DISABLED",
            "Volume Confirmed": True,
            "Live Volume Ratio": 0.0,
            "Volume Ratio Source": "DISABLED",
            "Volume Confirmation Note": (
                "Live volume confirmation is disabled."
            ),
            "Trading Session Mode": mode,
            "Elapsed Market Minutes": elapsed_minutes,
            "Volume Today": round(
                max(
                    current_volume,
                    ltp_volume_today,
                ),
                0,
            ),
            "20D Average Volume": round(
                average_volume,
                0,
            ),
            "Projected Full Session Volume": 0.0,
            "Volume Used For Ratio": 0.0,
            "Volume Calculation": "Disabled",
        }

    if (
        mode == "LIVE"
        and average_volume > 0
        and ltp_volume_today > 0
    ):
        volume_used = ltp_volume_today

        if (
            elapsed_minutes
            < LIVE_VOLUME_MIN_ELAPSED_MINUTES
        ):
            status = "PENDING"
            note = (
                "Not enough live-session time has elapsed "
                "for projected-volume confirmation."
            )
            calculation_text = (
                f"{ltp_volume_today:,.0f} current volume; "
                f"only {elapsed_minutes} market minutes elapsed."
            )
        else:
            projected_volume = (
                ltp_volume_today
                / elapsed_minutes
                * MARKET_SESSION_MINUTES
            )
            ratio = (
                projected_volume
                / average_volume
            )
            ratio_source = "PROJECTED LIVE VOLUME"
            note = (
                "Projected full-session volume compared "
                "with the 20-day daily average."
            )
            calculation_text = (
                f"Projected {projected_volume:,.0f} "
                f"÷ 20D average {average_volume:,.0f} "
                f"= {ratio:.2f}×"
            )

    elif (
        mode in {
            "CLOSED",
            "NON_TRADING_DAY",
            "PRE_OPEN",
        }
        and average_volume > 0
    ):
        # Prefer Current Volume because the historical-volume module
        # already supplies the latest completed daily volume. Fall back
        # to the Upstox quote volume only when Current Volume is absent.
        volume_used = (
            current_volume
            if current_volume > 0
            else ltp_volume_today
        )

        if volume_used > 0:
            ratio = (
                volume_used
                / average_volume
            )
            ratio_source = (
                "LATEST COMPLETED DAILY VOLUME"
            )
            note = (
                "Latest completed daily volume compared "
                "with the 20-day average."
            )
            calculation_text = (
                f"{volume_used:,.0f} "
                f"÷ {average_volume:,.0f} "
                f"= {ratio:.2f}×"
            )
        elif completed_ratio > 0:
            ratio = completed_ratio
            ratio_source = (
                "PRECALCULATED DAILY VOLUME RATIO"
            )
            note = (
                "Using the daily ratio calculated by "
                "the historical-volume module."
            )
            calculation_text = (
                f"Precalculated ratio = {ratio:.2f}×"
            )

    elif (
        average_volume > 0
        and ltp_volume_today > 0
    ):
        volume_used = ltp_volume_today
        ratio = (
            ltp_volume_today
            / average_volume
        )
        ratio_source = "RAW CURRENT-DAY VOLUME"
        note = (
            "Current-day cumulative volume compared "
            "with the 20-day average."
        )
        calculation_text = (
            f"{ltp_volume_today:,.0f} "
            f"÷ {average_volume:,.0f} "
            f"= {ratio:.2f}×"
        )

    if ratio > 0:
        if ratio >= LIVE_VOLUME_STRONG_RATIO:
            status = "STRONG"
        elif ratio >= LIVE_VOLUME_GOOD_RATIO:
            status = "GOOD"
        elif ratio >= LIVE_VOLUME_ACCEPTABLE_RATIO:
            status = "ACCEPTABLE"
        else:
            status = "WEAK"

        confirmed = (
            ratio
            >= LIVE_VOLUME_ACCEPTABLE_RATIO
        )

    return {
        "Volume Confirmation": status,
        "Volume Confirmed": confirmed,
        "Live Volume Ratio": round(
            ratio,
            2,
        ),
        "Volume Ratio Source": ratio_source,
        "Volume Confirmation Note": note,
        "Trading Session Mode": mode,
        "Elapsed Market Minutes": elapsed_minutes,
        "Volume Today": round(
            max(
                current_volume,
                ltp_volume_today,
            ),
            0,
        ),
        "20D Average Volume": round(
            average_volume,
            0,
        ),
        "Projected Full Session Volume": round(
            projected_volume,
            0,
        ),
        "Volume Used For Ratio": round(
            volume_used,
            0,
        ),
        "Volume Calculation": calculation_text,
    }

def _proximity_score(
    extension: float,
) -> float:
    distance = abs(
        extension
    )

    return max(
        0.0,
        100.0
        - min(
            distance,
            20.0,
        )
        * 5.0,
    )


def _confidence_score(
    row: pd.Series,
    extension: float,
    market_status: dict[str, Any] | None,
) -> float:
    quality = _number(
        row.get(
            "Trade Quality Score",
            0,
        )
    )
    rs = _number(
        row.get(
            "RS Score",
            0,
        )
    )
    sector = _number(
        row.get(
            "Sector RS Score",
            0,
        )
    )
    vcp = _number(
        row.get(
            "VCP Score",
            0,
        )
    )
    vcp = max(
        vcp,
        _number(row.get("Pattern Confidence", 0)),
        _number(row.get("Breakout Score", 0)),
    )
    volume = _number(
        row.get(
            "Volume Score",
            0,
        )
    )
    proximity = _proximity_score(
        extension
    )

    score = (
        quality
        * CONFIDENCE_WEIGHT_QUALITY
        + rs
        * CONFIDENCE_WEIGHT_RS
        + sector
        * CONFIDENCE_WEIGHT_SECTOR
        + vcp
        * CONFIDENCE_WEIGHT_VCP
        + volume
        * CONFIDENCE_WEIGHT_VOLUME
        + proximity
        * CONFIDENCE_WEIGHT_PROXIMITY
    )

    if market_status:
        status = str(
            market_status.get(
                "Market Status",
                "",
            )
        ).strip().upper()

        if status in {
            "CAUTIOUS",
            "NEUTRAL",
        }:
            score -= (
                CAUTIOUS_MARKET_CONFIDENCE_PENALTY
            )
        elif not bool(
            market_status.get(
                "Market Bullish",
                False,
            )
        ):
            score -= (
                BEARISH_MARKET_CONFIDENCE_PENALTY
            )

    return round(
        max(
            0.0,
            min(
                100.0,
                score,
            ),
        ),
        1,
    )


def _risk_level(
    stop_pct: float,
) -> str:
    if stop_pct <= LOW_RISK_STOP_PCT:
        return "LOW"

    if stop_pct >= HIGH_RISK_STOP_PCT:
        return "HIGH"

    return "MEDIUM"


def _recalculate_active_trade_plan(
    row: pd.Series,
) -> dict[str, Any]:
    """
    Recalculate active entry, stop, quantity and targets at BUY NOW.

    The original stop distance percentage is retained, but it is applied
    to the actual live execution reference price.
    """

    current = _number(
        row.get(
            "Current Price",
            0,
        )
    )
    suggested_entry = _number(
        row.get(
            "Suggested Entry",
            0,
        )
    )
    stop_pct = _number(
        row.get(
            "Stop Loss %",
            0,
        )
    )

    execution_entry = max(
        current,
        suggested_entry,
    )

    stop = execution_entry * (
        1
        - stop_pct / 100
    )

    risk_per_share = (
        execution_entry
        - stop
    )

    maximum_rupee_risk = (
        ACCOUNT_CAPITAL
        * RISK_PER_TRADE_PCT
        / 100
    )

    if (
        execution_entry <= 0
        or risk_per_share <= 0
    ):
        return {
            "Trade Plan Recalculated": False,
        }

    quantity_by_risk = math.floor(
        maximum_rupee_risk
        / risk_per_share
    )

    quantity_by_capital = math.floor(
        ACCOUNT_CAPITAL
        / execution_entry
    )

    quantity = max(
        0,
        min(
            quantity_by_risk,
            quantity_by_capital,
        ),
    )

    investment = (
        quantity
        * execution_entry
    )

    actual_risk = (
        quantity
        * risk_per_share
    )

    return {
        "Trade Plan Recalculated": True,
        "Execution Entry": round(
            execution_entry,
            2,
        ),
        "Suggested Entry": round(
            execution_entry,
            2,
        ),
        "Suggested Stop Loss": round(
            stop,
            2,
        ),
        "Risk Per Share": round(
            risk_per_share,
            2,
        ),
        "Suggested Quantity": quantity,
        "Planned Investment": round(
            investment,
            2,
        ),
        "Actual Rupee Risk": round(
            actual_risk,
            2,
        ),
        "1R Price": round(
            execution_entry
            + risk_per_share,
            2,
        ),
        "Target 1:2": round(
            execution_entry
            + 2
            * risk_per_share,
            2,
        ),
        "Target 1:3": round(
            execution_entry
            + 3
            * risk_per_share,
            2,
        ),
        "Breakeven Stop": round(
            execution_entry
            * 0.9975,
            2,
        ),
    }


def _decision_for_row(
    row: pd.Series,
    market_status: dict[str, Any] | None,
) -> dict[str, Any]:
    current = _number(
        row.get(
            "Current Price",
            0,
        )
    )
    entry = _number(
        row.get(
            "Suggested Entry",
            0,
        )
    )
    stop = _number(
        row.get(
            "Suggested Stop Loss",
            0,
        )
    )
    stop_pct = _number(
        row.get(
            "Stop Loss %",
            99,
        )
    )

    if (
        current <= 0
        or entry <= 0
    ):
        return {
            "Action": "AVOID",
            "Entry Status": "Invalid price data",
            "Entry Window": "NONE",
            "Risk Level": "HIGH",
            "Decision Confidence": 0.0,
            "Decision Reason": (
                "Current price or planned entry is unavailable."
            ),
            "Trade Urgency": "LOW PRIORITY",
            "Stop Type": "NOT APPLICABLE",
            "Trade Plan Status": "NO NEW TRADE",
            "Show Active Trade Plan": False,
            "Show Provisional Trade Plan": False,
            "Hide Trade Plan": True,
            **_volume_metrics(row),
        }

    if (
        stop <= 0
        or stop >= entry
    ):
        return {
            "Action": "AVOID",
            "Entry Status": "Invalid planned stop",
            "Entry Window": "NONE",
            "Risk Level": "HIGH",
            "Decision Confidence": 0.0,
            "Decision Reason": (
                "Planned stop is missing or is not below entry."
            ),
            "Trade Urgency": "LOW PRIORITY",
            "Stop Type": "NOT APPLICABLE",
            "Trade Plan Status": "NO NEW TRADE",
            "Show Active Trade Plan": False,
            "Show Provisional Trade Plan": False,
            "Hide Trade Plan": True,
            **_volume_metrics(row),
        }

    extension = (
        (
            current
            - entry
        )
        / entry
        * 100
    )

    below = max(
        0.0,
        -extension,
    )

    volume_fields = (
        _volume_metrics(row)
    )

    confidence = (
        _confidence_score(
            row,
            extension,
            market_status,
        )
    )

    risk = _risk_level(
        stop_pct
    )
    ema_bullish = bool(
        row.get(
            "EMA Bullish Alignment",
            False,
        )
    )

    action = "AVOID"
    entry_status = ""
    entry_window = "NONE"
    reason = ""
    urgency = "LOW PRIORITY"

    if extension > MAX_ALLOWED_EXTENSION_PCT:
        action = (
            "EXTENDED / DO NOT CHASE"
        )
        entry_status = (
            f"{extension:.2f}% above entry"
        )
        entry_window = "EXPIRED"
        reason = (
            "Price is beyond the maximum fresh-entry "
            "extension. Do not chase."
        )
        urgency = "WAIT FOR NEW BASE"

    elif (
        0
        <= extension
        <= MAX_BUY_EXTENSION_PCT
    ):
        if (
            confidence
            >= MIN_BUY_CONFIDENCE
            and (
                not LIVE_BUY_REQUIRES_VOLUME
                or bool(
                    volume_fields[
                        "Volume Confirmed"
                    ]
                )
            )
        ):
            action = "BUY NOW"
            entry_status = (
                "Entry triggered; "
                f"{extension:.2f}% above entry"
            )
            entry_window = "TODAY"
            reason = (
                "Price, quality and live-volume rules "
                "meet the configured BUY NOW conditions."
            )
            urgency = "IMMEDIATE"
        else:
            action = (
                "BREAKOUT / VOLUME PENDING"
            )
            entry_status = (
                "Breakout active; "
                f"{extension:.2f}% above entry"
            )
            entry_window = "ACTIVE"
            if (
                LIVE_BUY_REQUIRES_VOLUME
                and not bool(
                    volume_fields[
                        "Volume Confirmed"
                    ]
                )
            ):
                reason = (
                    "Price has triggered, but live volume "
                    "is not confirmed. Do not initiate a "
                    "fresh position yet."
                )
            else:
                reason = (
                    "Breakout is active, but confidence "
                    "is below the fresh-buy threshold."
                )
            urgency = (
                "VOLUME CONFIRMATION PENDING"
            )

    elif (
        below
        <= LIVE_NEAR_TRIGGER_PCT
        and confidence
        >= MIN_WATCH_CONFIDENCE
    ):
        entry_status = (
            f"{below:.2f}% below entry"
        )
        if risk == "HIGH" or not ema_bullish:
            action = "WATCH"
            entry_window = "WATCH"
            reasons = []
            if risk == "HIGH":
                reasons.append(
                    "the provisional stop is high risk"
                )
            if not ema_bullish:
                reasons.append(
                    "EMA alignment is mixed"
                )
            reason = (
                "Price is near the trigger, but "
                + " and ".join(reasons)
                + ". Keep it on WATCH rather than treating "
                "it as an immediate near-trigger setup."
            )
            urgency = "WATCHLIST"
        else:
            action = "NEAR TRIGGER"
            entry_window = "NEXT 1–2 SESSIONS"
            reason = (
                "Price is close to entry. Wait for the trigger "
                "and acceptable volume."
            )
            urgency = "NEXT 1–2 SESSIONS"

    elif (
        below
        <= LIVE_WATCH_BELOW_ENTRY_PCT
        and confidence
        >= MIN_WATCH_CONFIDENCE
    ):
        action = "WATCH"
        entry_status = (
            f"{below:.2f}% below entry"
        )
        entry_window = "WATCH"
        reason = (
            "Pattern remains valid, but the entry is not "
            "close enough for immediate action."
        )
        urgency = "WATCHLIST"

    elif (
        below
        <= LIVE_WAIT_MAX_BELOW_ENTRY_PCT
        and confidence
        >= MIN_WATCH_CONFIDENCE
    ):
        action = "WAIT"
        entry_status = (
            f"{below:.2f}% below entry"
        )
        entry_window = "WAIT"
        reason = (
            "Good pattern, but price remains too far from "
            "the planned trigger."
        )
        urgency = "WAIT FOR TRIGGER"

    else:
        action = "AVOID"
        entry_status = (
            f"{below:.2f}% below entry"
        )
        entry_window = "NONE"
        reason = (
            "The setup is too far from entry or confidence "
            "is below the configured watch threshold."
        )
        urgency = "LOW PRIORITY"

    circuit_fields = _circuit_metrics(
        row,
        current,
        entry,
    )

    circuit_blocks_entry = bool(
        circuit_fields[
            "Upper Circuit Blocked"
        ]
        or circuit_fields[
            "Entry Above Upper Circuit"
        ]
    )

    if (
        circuit_blocks_entry
        and action == "BUY NOW"
    ):
        action = "WATCH"
        entry_window = "NOT EXECUTABLE TODAY"
        urgency = "UPPER CIRCUIT RISK"
        reason = (
            circuit_fields[
                "Circuit Execution Note"
            ]
            + " BUY NOW was downgraded to WATCH."
        )
    elif (
        circuit_fields[
            "Entry Above Upper Circuit"
        ]
        and action == "NEAR TRIGGER"
    ):
        action = "WATCH"
        entry_window = "NOT REACHABLE TODAY"
        urgency = "UPPER CIRCUIT RISK"
        reason = (
            circuit_fields[
                "Circuit Execution Note"
            ]
            + " Keep it on WATCH for a later session."
        )

    if not bool(
        row.get(
            "Fundamentals Eligible",
            True,
        )
    ):
        action = "AVOID"
        entry_window = "NONE"
        urgency = "FUNDAMENTALS BLOCK"
        reason = (
            "The mandatory fundamentals gate did not pass: "
            + str(
                row.get(
                    "Fundamentals Gate Status",
                    "FAIL",
                )
            )
        )
    elif not bool(
        row.get(
            "Base Stage Pass",
            True,
        )
    ):
        action = "AVOID"
        entry_window = "NONE"
        urgency = "LATE-STAGE BASE"
        reason = (
            f"Base stage {int(row.get('Base Stage', 0) or 0)} "
            "exceeds the configured maximum for a fresh entry."
        )

    active = (
        action == "BUY NOW"
    )
    provisional = action in {
        "NEAR TRIGGER",
        "WATCH",
        "WAIT",
    }
    hidden = action in {
        "EXTENDED / DO NOT CHASE",
        "AVOID",
    }

    decision = {
        "Action": action,
        "Entry Status": entry_status,
        "Entry Window": entry_window,
        "Risk Level": risk,
        "Decision Confidence": confidence,
        "Decision Reason": reason,
        "Trade Urgency": urgency,
        "Live Extension %": round(
            extension,
            2,
        ),
        "Stop Type": (
            "ACTIVE"
            if active
            else "PROVISIONAL"
            if provisional
            else "NOT APPLICABLE"
        ),
        "Trade Plan Status": (
            "ENTRY TRIGGERED"
            if active
            else "WAITING FOR ENTRY"
            if provisional
            else "NO NEW TRADE"
        ),
        "Show Active Trade Plan": active,
        "Show Provisional Trade Plan": provisional,
        "Hide Trade Plan": hidden,
        **volume_fields,
        **circuit_fields,
    }

    if active:
        decision.update(
            _recalculate_active_trade_plan(
                row
            )
        )
    else:
        decision[
            "Trade Plan Recalculated"
        ] = False

    return decision


def add_trade_decisions(
    report: pd.DataFrame,
    market_status: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Add V3.3 live-trading decisions after the Upstox LTP overlay.

    This function intentionally runs after trade-quality calculations.
    """

    frame = report.copy()

    decision_rows = [
        _decision_for_row(
            row,
            market_status,
        )
        for _, row
        in frame.iterrows()
    ]

    decisions = pd.DataFrame(
        decision_rows,
        index=frame.index,
    )

    for column in decisions.columns:
        frame[column] = (
            decisions[column]
        )

    frame["Decision Priority"] = (
        frame["Action"]
        .map(ACTION_PRIORITY)
        .fillna(0)
        .astype(int)
    )

    frame["Action Priority"] = (
        frame["Decision Priority"]
    )

    frame["Confidence Score"] = (
        frame[
            "Decision Confidence"
        ]
    )

    return frame
