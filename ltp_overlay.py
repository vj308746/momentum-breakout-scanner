from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from config import (
    BREAKOUT_VOLUME_THRESHOLD,
    CIRCUIT_GUARD_ENABLED,
    LTP_BATCH_SIZE,
    LTP_VOLUME_UPDATE_AFTER_HOUR,
    LTP_VOLUME_UPDATE_AFTER_MINUTE,
    MAX_PIVOT_EXTENSION_PCT,
    NEAR_PIVOT_THRESHOLD_PCT,
)
from upstox_client import UpstoxClient


TREND_CONDITION_COLUMNS = [
    "Price > 50 DMA",
    "Price > 150 DMA",
    "Price > 200 DMA",
    "50 DMA > 150 DMA",
    "150 DMA > 200 DMA",
    "200 DMA Rising",
    "30% Above 52W Low",
    "Within 25% of 52W High",
]


def fetch_ltp_quotes(
    instrument_keys: list[str],
    client: UpstoxClient | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Fetch Upstox LTP V3 quotes in batches and return a map keyed by
    the official Upstox instrument token.

    Upstox may use a display symbol as the outer response key, so the
    value's `instrument_token` field is used as the canonical key.
    """

    clean_keys = list(
        dict.fromkeys(
            key.strip()
            for key in instrument_keys
            if key and key.strip()
        )
    )

    if not clean_keys:
        return {}

    api_client = client or UpstoxClient()
    quotes: dict[str, dict[str, Any]] = {}

    for start in range(0, len(clean_keys), LTP_BATCH_SIZE):
        batch = clean_keys[start:start + LTP_BATCH_SIZE]
        if CIRCUIT_GUARD_ENABLED:
            try:
                payload = api_client.get_full_market_quotes(
                    batch
                )
            except Exception:
                logging.exception(
                    "Full Market Quotes failed; falling back "
                    "to LTP V3 without circuit data."
                )
                payload = api_client.get_ltp(batch)
        else:
            payload = api_client.get_ltp(batch)

        for response_key, raw_quote in payload.items():
            if not isinstance(raw_quote, dict):
                continue

            quote = dict(raw_quote)
            instrument_token = str(
                quote.get("instrument_token", "")
            ).strip()

            if instrument_token:
                quotes[instrument_token] = quote

            # Retain the response key as a secondary lookup.
            quotes[str(response_key).strip()] = quote

    return quotes


def quote_for_instrument(
    quotes: dict[str, dict[str, Any]],
    instrument_key: str,
) -> dict[str, Any] | None:
    direct = quotes.get(instrument_key)
    if direct is not None:
        return direct

    for quote in quotes.values():
        if str(
            quote.get("instrument_token", "")
        ).strip() == instrument_key:
            return quote

    return None


def _as_float(
    value: Any,
    default: float | None = None,
) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default

    if pd.isna(numeric):
        return default

    return numeric


def _after_market_close() -> bool:
    now = datetime.now(
        ZoneInfo("Asia/Kolkata")
    )
    cutoff = now.replace(
        hour=LTP_VOLUME_UPDATE_AFTER_HOUR,
        minute=LTP_VOLUME_UPDATE_AFTER_MINUTE,
        second=0,
        microsecond=0,
    )
    return now >= cutoff


def apply_stock_ltp_overlay(
    result: dict[str, Any],
    quote: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Overlay real-time/current LTP on a completed historical analysis.

    Historical candles continue to drive DMA, RS, VCP and stop calculations.
    Price-dependent trend/pivot fields are recalculated using the LTP.
    """

    updated = dict(result)

    if not quote:
        updated["LTP Overlay Applied"] = False
        updated["Current Price Source"] = "Historical candle"
        return updated

    ltp = _as_float(quote.get("last_price"))
    if ltp is None or ltp <= 0:
        updated["LTP Overlay Applied"] = False
        updated["Current Price Source"] = "Historical candle"
        return updated

    previous_close = _as_float(quote.get("cp"))
    live_volume = _as_float(quote.get("volume"))
    last_traded_quantity = _as_float(quote.get("ltq"))
    upper_circuit = _as_float(
        quote.get("upper_circuit_limit")
    )
    lower_circuit = _as_float(
        quote.get("lower_circuit_limit")
    )
    total_sell_quantity = _as_float(
        quote.get("total_sell_quantity")
    )
    total_buy_quantity = _as_float(
        quote.get("total_buy_quantity")
    )

    updated["Historical Last Close"] = updated.get(
        "Current Price"
    )
    updated["Current Price"] = round(ltp, 2)
    updated["Current Price Source"] = "Upstox LTP V3"
    updated["LTP Overlay Applied"] = True
    updated["LTP Previous Close"] = (
        round(previous_close, 2)
        if previous_close is not None
        else None
    )
    updated["LTP Change %"] = (
        round(
            ((ltp / previous_close) - 1) * 100,
            2,
        )
        if previous_close
        else None
    )
    updated["LTP Volume Today"] = (
        round(live_volume, 0)
        if live_volume is not None
        else None
    )
    updated["LTP Last Traded Quantity"] = (
        round(last_traded_quantity, 0)
        if last_traded_quantity is not None
        else None
    )
    updated["Upper Circuit"] = (
        round(upper_circuit, 2)
        if upper_circuit is not None
        and upper_circuit > 0
        else None
    )
    updated["Lower Circuit"] = (
        round(lower_circuit, 2)
        if lower_circuit is not None
        and lower_circuit > 0
        else None
    )
    updated["Total Sell Quantity"] = (
        round(total_sell_quantity, 0)
        if total_sell_quantity is not None
        else None
    )
    updated["Total Buy Quantity"] = (
        round(total_buy_quantity, 0)
        if total_buy_quantity is not None
        else None
    )
    updated["Circuit Data Available"] = bool(
        upper_circuit is not None
        and upper_circuit > 0
    )

    # Include a new live high in the 52-week range when applicable.
    high_52 = max(
        float(updated["52W High"]),
        ltp,
    )
    low_52 = min(
        float(updated["52W Low"]),
        ltp,
    )
    updated["52W High"] = round(high_52, 2)
    updated["52W Low"] = round(low_52, 2)
    updated["% Above 52W Low"] = round(
        ((ltp - low_52) / low_52) * 100,
        2,
    )
    updated["% Below 52W High"] = round(
        ((high_52 - ltp) / high_52) * 100,
        2,
    )

    # Recalculate only price-dependent trend-template conditions.
    updated["Price > 50 DMA"] = (
        ltp > float(updated["50 DMA"])
    )
    updated["Price > 150 DMA"] = (
        ltp > float(updated["150 DMA"])
    )
    updated["Price > 200 DMA"] = (
        ltp > float(updated["200 DMA"])
    )
    updated["30% Above 52W Low"] = (
        updated["% Above 52W Low"] >= 30
    )
    updated["Within 25% of 52W High"] = (
        updated["% Below 52W High"] <= 25
    )

    passed = sum(
        bool(updated.get(column, False))
        for column in TREND_CONDITION_COLUMNS
    )
    total = len(TREND_CONDITION_COLUMNS)
    updated["Conditions Passed"] = passed
    updated["Total Conditions"] = total
    updated["Score %"] = round(
        passed / total * 100,
        2,
    )
    updated["Trend Template Pass"] = (
        passed == total
    )

    # Recalculate pivot-distance and breakout fields using LTP.
    pivot = _as_float(updated.get("Pivot Price"))
    if pivot and pivot > 0:
        distance = (
            (pivot - ltp) / pivot
        ) * 100
        extension = (
            (ltp - pivot) / pivot
        ) * 100

        updated["Distance From Pivot %"] = round(
            distance,
            2,
        )
        updated["Pivot Extension %"] = round(
            extension,
            2,
        )
        updated["Near Pivot"] = (
            0 <= distance
            <= NEAR_PIVOT_THRESHOLD_PCT
        )
        updated["Pivot Breakout"] = (
            ltp > pivot
        )
        updated["Breakout Not Extended"] = (
            updated["Pivot Breakout"]
            and extension
            <= MAX_PIVOT_EXTENSION_PCT
        )

    # Trade Planner entry is pivot-based; only its distance from live
    # price needs refreshing.
    suggested_entry = _as_float(
        updated.get("Suggested Entry")
    )
    if suggested_entry and suggested_entry > 0:
        updated["Entry Distance %"] = round(
            (
                (suggested_entry - ltp)
                / suggested_entry
            )
            * 100,
            2,
        )

    # After the market closes, Upstox cumulative daily volume is
    # comparable to normal daily-volume averages. In the morning it
    # is deliberately not used as a full-day breakout confirmation.
    if (
        _after_market_close()
        and live_volume is not None
        and live_volume >= 0
    ):
        avg_20 = _as_float(
            updated.get("20D Avg Volume")
        )
        updated["Current Volume"] = round(
            live_volume,
            0,
        )

        if avg_20 and avg_20 > 0:
            current_ratio = live_volume / avg_20
            updated["Current Volume Ratio"] = round(
                current_ratio,
                2,
            )
            updated["Breakout Volume Pass"] = (
                current_ratio
                >= BREAKOUT_VOLUME_THRESHOLD
            )

    return updated


def apply_market_ltp_overlay(
    market_status: dict[str, Any],
    quote: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Refresh only the displayed benchmark price. The cautious/bullish
    classification remains based on completed daily trend structure.
    """

    updated = dict(market_status)

    if not quote:
        updated["Market Price Source"] = (
            "Historical candle"
        )
        return updated

    ltp = _as_float(quote.get("last_price"))
    if ltp is None or ltp <= 0:
        updated["Market Price Source"] = (
            "Historical candle"
        )
        return updated

    updated["Historical Market Close"] = (
        updated.get("Market Price")
    )
    updated["Market Price"] = round(ltp, 2)
    updated["Market Price Source"] = (
        "Upstox LTP V3"
    )

    previous_close = _as_float(
        quote.get("cp")
    )
    updated["Market Change %"] = (
        round(
            ((ltp / previous_close) - 1) * 100,
            2,
        )
        if previous_close
        else None
    )

    return updated
