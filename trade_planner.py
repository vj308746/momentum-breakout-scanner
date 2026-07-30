from __future__ import annotations

import math
from typing import Any

import pandas as pd

from config import (
    ACCOUNT_CAPITAL,
    ATR_PERIOD,
    ATR_STOP_MULTIPLIER,
    ENTRY_BUFFER_PCT,
    MAX_STOP_LOSS_PCT,
    MIN_STOP_LOSS_PCT,
    RISK_PER_TRADE_PCT,
    STOP_LOOKBACK_DAYS,
)


def _calculate_atr(
    data: pd.DataFrame,
    period: int = ATR_PERIOD,
) -> float:
    required = {"High", "Low", "Close"}
    missing = required.difference(data.columns)

    if missing:
        raise RuntimeError(
            "ATR calculation is missing columns: "
            + ", ".join(sorted(missing))
        )

    frame = data[["High", "Low", "Close"]].dropna().copy()

    if len(frame) < period + 1:
        raise RuntimeError(
            f"At least {period + 1} records are required for ATR."
        )

    previous_close = frame["Close"].shift(1)

    true_range = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - previous_close).abs(),
            (frame["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = float(true_range.tail(period).mean())

    if pd.isna(atr) or atr <= 0:
        raise RuntimeError("Unable to calculate a valid ATR.")

    return atr


def _ema(
    close: pd.Series,
    span: int,
) -> float:
    value = float(
        close.ewm(
            span=span,
            adjust=False,
        ).mean().iloc[-1]
    )

    if pd.isna(value) or value <= 0:
        raise RuntimeError(
            f"Unable to calculate EMA {span}."
        )

    return value


def calculate_trade_plan(
    data: pd.DataFrame,
    pivot_price: float,
) -> dict[str, Any]:
    """
    Build a risk-controlled trade plan.

    Historical candles are used for:
    - pivot-based entry
    - ATR and technical stop
    - 10, 20 and 50 EMA
    - quantity and reward targets

    The LTP overlay later refreshes current-price distances and decisions.
    """

    if pivot_price <= 0:
        raise RuntimeError("Pivot price must be positive.")

    required = ["High", "Low", "Close"]
    clean = data[required].dropna().copy()

    minimum_rows = max(
        STOP_LOOKBACK_DAYS,
        ATR_PERIOD + 1,
        50,
    )

    if len(clean) < minimum_rows:
        raise RuntimeError(
            "Insufficient data for trade planning."
        )

    historical_close = float(
        clean["Close"].iloc[-1]
    )

    entry = float(
        pivot_price
        * (
            1
            + ENTRY_BUFFER_PCT / 100
        )
    )

    atr = _calculate_atr(clean)

    recent_low = float(
        clean["Low"]
        .tail(STOP_LOOKBACK_DAYS)
        .min()
    )

    atr_stop = (
        entry
        - ATR_STOP_MULTIPLIER * atr
    )

    widest_allowed_stop = (
        entry
        * (
            1
            - MAX_STOP_LOSS_PCT / 100
        )
    )

    tightest_allowed_stop = (
        entry
        * (
            1
            - MIN_STOP_LOSS_PCT / 100
        )
    )

    technical_stop = max(
        recent_low,
        atr_stop,
        widest_allowed_stop,
    )

    stop = min(
        technical_stop,
        tightest_allowed_stop,
    )

    if stop >= entry:
        stop = tightest_allowed_stop

    risk_per_share = entry - stop

    if risk_per_share <= 0:
        raise RuntimeError(
            "Calculated risk per share is not positive."
        )

    stop_pct = (
        risk_per_share / entry
    ) * 100

    maximum_rupee_risk = (
        ACCOUNT_CAPITAL
        * RISK_PER_TRADE_PCT
        / 100
    )

    quantity_by_risk = math.floor(
        maximum_rupee_risk
        / risk_per_share
    )

    quantity_by_capital = math.floor(
        ACCOUNT_CAPITAL / entry
    )

    quantity = max(
        0,
        min(
            quantity_by_risk,
            quantity_by_capital,
        ),
    )

    investment = quantity * entry
    actual_risk = (
        quantity * risk_per_share
    )

    one_r = (
        entry + risk_per_share
    )
    two_r = (
        entry + 2 * risk_per_share
    )
    three_r = (
        entry + 3 * risk_per_share
    )

    breakeven_stop = (
        entry * 0.9975
    )

    close_series = (
        clean["Close"]
        .astype(float)
    )

    ema_10 = _ema(
        close_series,
        10,
    )
    ema_20 = _ema(
        close_series,
        20,
    )
    ema_50 = _ema(
        close_series,
        50,
    )

    ema_alignment = (
        ema_10 > ema_20 > ema_50
    )

    plan_valid = (
        quantity > 0
        and MIN_STOP_LOSS_PCT
        <= stop_pct
        <= MAX_STOP_LOSS_PCT
        and stop < entry
    )

    return {
        "Account Capital": round(
            ACCOUNT_CAPITAL,
            2,
        ),
        "Risk Per Trade %": round(
            RISK_PER_TRADE_PCT,
            2,
        ),
        "Maximum Rupee Risk": round(
            maximum_rupee_risk,
            2,
        ),
        "Suggested Entry": round(
            entry,
            2,
        ),
        "Entry Distance %": round(
            (
                (
                    entry
                    - historical_close
                )
                / entry
            )
            * 100,
            2,
        ),
        "ATR 14": round(
            atr,
            2,
        ),
        "ATR % of Entry": round(
            atr / entry * 100,
            2,
        ),
        "Recent 10D Low": round(
            recent_low,
            2,
        ),
        "ATR Stop": round(
            atr_stop,
            2,
        ),
        "Suggested Stop Loss": round(
            stop,
            2,
        ),
        "Stop Type": "PROVISIONAL",
        "Trade Plan Status": "WAITING FOR ENTRY",
        "Stop Loss %": round(
            stop_pct,
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
            one_r,
            2,
        ),
        "Target 1:2": round(
            two_r,
            2,
        ),
        "Target 1:3": round(
            three_r,
            2,
        ),
        "Breakeven Stop": round(
            breakeven_stop,
            2,
        ),
        "EMA 10": round(
            ema_10,
            2,
        ),
        "EMA 20": round(
            ema_20,
            2,
        ),
        "EMA 50": round(
            ema_50,
            2,
        ),
        "EMA Bullish Alignment": (
            ema_alignment
        ),
        "Historical Price vs EMA 10 %": round(
            (
                historical_close
                / ema_10
                - 1
            )
            * 100,
            2,
        ),
        "Historical Price vs EMA 20 %": round(
            (
                historical_close
                / ema_20
                - 1
            )
            * 100,
            2,
        ),
        "Historical Price vs EMA 50 %": round(
            (
                historical_close
                / ema_50
                - 1
            )
            * 100,
            2,
        ),
        "Trailing Stop Plan": (
            "Keep the initial stop until +1R. "
            "At +1R, move the stop near breakeven. "
            "After +2R, trail using the higher of "
            "the 10-day low or 20 EMA."
        ),
        "Trade Plan Valid": (
            plan_valid
        ),
    }
