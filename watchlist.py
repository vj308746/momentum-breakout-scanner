from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from config import (
    ACCOUNT_CAPITAL,
    DECISION_WATCHLIST_SIZE,
    RISK_PER_TRADE_PCT,
    SHOW_EMA_PANEL,
    SHOW_VOLUME_PANEL,
    STOCK_UNIVERSE_NAME,
)


def _optional_percent(
    value: object,
) -> str:
    numeric = pd.to_numeric(
        value,
        errors="coerce",
    )
    if pd.isna(numeric):
        return "N/A"
    return f"{float(numeric):.1f}%"


def select_watchlist_candidates(
    report: pd.DataFrame,
) -> pd.DataFrame:
    """
    Select independently validated breakout and momentum candidates.
    """

    core_eligible = report.get(
        "Breakout Scanner Eligible",
        pd.Series(False, index=report.index),
    ).fillna(False).astype(bool)
    fundamentals_eligible = report.get(
        "Fundamentals Eligible",
        pd.Series(True, index=report.index),
    ).fillna(False).astype(bool)
    core_eligible &= fundamentals_eligible

    allowed_actions = {
        "BUY NOW",
        "NEAR TRIGGER",
        "WATCH",
        "WAIT",
        "BREAKOUT / VOLUME PENDING",
    }

    eligible = report[
        core_eligible
        & report[
            "Action"
        ].isin(
            allowed_actions
        )
    ].copy()

    if eligible.empty:
        empty = report.head(0).copy()
        empty.attrs["eligible_count"] = 0
        empty.attrs["displayed_count"] = 0
        return empty

    eligible_count = len(eligible)

    eligible[
        "Entry Proximity Score"
    ] = (
        100
        - eligible[
            "Live Extension %"
        ]
        .abs()
        .clip(
            upper=20
        )
        * 5
    ).clip(
        lower=0,
        upper=100,
    )

    eligible[
        "Priority Score"
    ] = (
        eligible[
            "Trade Quality Score"
        ]
        * 0.30
        + eligible[
            "Confidence Score"
        ]
        * 0.20
        + eligible[
            "Entry Proximity Score"
        ]
        * 0.20
        + eligible[
            "RS Score"
        ]
        * 0.10
        + eligible[
            "Sector RS Score"
        ]
        * 0.10
        + eligible.get(
            "Pattern Confidence",
            pd.Series(0.0, index=eligible.index),
        ).fillna(0)
        * 0.10
        + eligible.get(
            "Breakout Score",
            pd.Series(0.0, index=eligible.index),
        ).fillna(0)
        * 0.15
        + (
            eligible.get(
                "Multi-Pattern Confirmation",
                pd.Series(False, index=eligible.index),
            ).fillna(False).astype(float)
            * 100
        )
        * 0.05
    ).round(1)

    eligible = eligible.sort_values(
        by=[
            "Action Priority",
            "Priority Score",
            "Confidence Score",
            "Trade Quality Score",
            "RS Score",
            "Volume Score",
            "Pattern Confidence",
            "VCP Score",
        ],
        ascending=[
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
        ],
    )

    watchlist = (
        eligible
        .head(
            DECISION_WATCHLIST_SIZE
        )
        .copy()
        .reset_index(
            drop=True
        )
    )

    watchlist.insert(
        0,
        "Watchlist Rank",
        range(
            1,
            len(watchlist) + 1,
        ),
    )

    watchlist.attrs["eligible_count"] = eligible_count
    watchlist.attrs["displayed_count"] = len(watchlist)

    return watchlist


def _action_icon(
    action: str,
) -> str:
    return {
        "BUY NOW": "🟢",
        "NEAR TRIGGER": "🟡",
        "WATCH": "🔵",
        "WAIT": "⚪",
        "BREAKOUT / VOLUME PENDING": "🟣",
        "EXTENDED / DO NOT CHASE": "🟠",
        "AVOID": "🔴",
    }.get(
        action,
        "⚪",
    )


def _summary_lines(
    watchlist: pd.DataFrame,
) -> list[str]:
    order = [
        "BUY NOW",
        "NEAR TRIGGER",
        "WATCH",
        "WAIT",
        "BREAKOUT / VOLUME PENDING",
    ]

    lines = [
        "DECISION SUMMARY",
    ]

    for action in order:
        count = int(
            watchlist[
                "Action"
            ].eq(
                action
            ).sum()
        )

        if count:
            lines.append(
                f"{_action_icon(action)} "
                f"{action}: {count}"
            )

    return lines


def _confidence_value(
    row: pd.Series,
) -> float:
    return float(
        row.get(
            "Decision Confidence",
            row.get(
                "Confidence Score",
                0,
            ),
        )
        or 0
    )


def _append_trade_plan_lines(
    lines: list[str],
    row: pd.Series,
) -> None:
    if bool(
        row.get(
            "Hide Trade Plan",
            False,
        )
    ):
        lines.extend(
            [
                "Trade Plan",
                "Status: No valid fresh entry",
            ]
        )
        return

    if bool(
        row.get(
            "Show Active Trade Plan",
            False,
        )
    ):
        lines.extend(
            [
                "Trade Plan",
                "Status: Entry triggered",
                (
                    f"Entry "
                    f"₹{row['Suggested Entry']:.2f} | "
                    f"Active Stop "
                    f"₹{row['Suggested Stop Loss']:.2f} "
                    f"({row['Stop Loss %']:.2f}%)"
                ),
                (
                    f"Qty "
                    f"{int(row['Suggested Quantity'])} | "
                    f"Investment "
                    f"₹{row['Planned Investment']:,.2f} | "
                    f"Planned loss "
                    f"₹{row['Actual Rupee Risk']:,.2f}"
                ),
                (
                    f"Target 1:2 "
                    f"₹{row['Target 1:2']:.2f} | "
                    f"Target 1:3 "
                    f"₹{row['Target 1:3']:.2f}"
                ),
            ]
        )
        return

    lines.extend(
        [
            "Trade Plan",
            "Status: Waiting for breakout",
            (
                f"Provisional Stop "
                f"₹{row['Suggested Stop Loss']:.2f} "
                f"({row['Stop Loss %']:.2f}%) | "
                f"Risk: "
                f"{row['Risk Level']}"
            ),
            (
                "Final stop, quantity and targets will "
                "be recalculated only after the entry triggers."
            ),
        ]
    )


def _append_volume_lines(
    lines: list[str],
    row: pd.Series,
) -> None:
    status = str(
        row.get(
            "Volume Confirmation",
            "PENDING",
        )
    )

    ratio = float(
        row.get(
            "Live Volume Ratio",
            0,
        )
        or 0
    )

    source = str(
        row.get(
            "Volume Ratio Source",
            "UNAVAILABLE",
        )
    )

    volume_today = float(
        row.get(
            "Volume Used For Ratio",
            row.get(
                "Volume Today",
                0,
            ),
        )
        or 0
    )

    average_volume = float(
        row.get(
            "20D Average Volume",
            row.get(
                "20D Avg Volume",
                0,
            ),
        )
        or 0
    )

    projected_volume = float(
        row.get(
            "Projected Full Session Volume",
            0,
        )
        or 0
    )

    calculation = str(
        row.get(
            "Volume Calculation",
            "",
        )
    ).strip()

    session_mode = str(
        row.get(
            "Trading Session Mode",
            "UNKNOWN",
        )
    )

    icon = (
        "✅"
        if bool(
            row.get(
                "Volume Confirmed",
                False,
            )
        )
        else "⏳"
        if status == "PENDING"
        else "⚠"
    )

    lines.append(
        (
            f"Volume Confirmation: "
            f"{icon} {status}"
            + (
                f" | Ratio {ratio:.2f}×"
                if ratio > 0
                else ""
            )
        )
    )

    lines.append(
        (
            f"Volume Used "
            f"{volume_today:,.0f} | "
            f"20D Avg "
            f"{average_volume:,.0f}"
        )
    )

    if projected_volume > 0:
        lines.append(
            (
                f"Projected Full-Session Volume "
                f"{projected_volume:,.0f}"
            )
        )

    lines.append(
        (
            f"Volume basis: {source} | "
            f"Session: {session_mode}"
        )
    )

    if calculation:
        lines.append(
            f"Volume calculation: {calculation}"
        )


def _append_circuit_lines(
    lines: list[str],
    row: pd.Series,
) -> None:
    available = bool(
        row.get(
            "Circuit Data Available",
            False,
        )
    )

    if not available:
        lines.append(
            "Circuit check: unavailable — confirm in Upstox."
        )
        return

    upper = float(
        row.get("Upper Circuit", 0)
        or 0
    )
    lower = float(
        row.get("Lower Circuit", 0)
        or 0
    )
    distance = float(
        row.get(
            "Distance To Upper Circuit %",
            0,
        )
        or 0
    )
    status = str(
        row.get(
            "Circuit Execution Status",
            "UNAVAILABLE",
        )
    )
    note = str(
        row.get(
            "Circuit Execution Note",
            "",
        )
    ).strip()

    icon = (
        "⛔"
        if status in {
            "UPPER CIRCUIT BLOCK",
            "ENTRY UNREACHABLE TODAY",
        }
        else "⚠"
        if status == "UPPER CIRCUIT CAUTION"
        else "✅"
    )

    limits = (
        f"Upper ₹{upper:.2f}"
        + (
            f" | Lower ₹{lower:.2f}"
            if lower > 0
            else ""
        )
        + f" | Distance {distance:.2f}%"
    )

    lines.append(
        f"Execution Check: {icon} {status}"
    )
    lines.append(
        f"Price band: {limits}"
    )
    if note and status != "CLEAR":
        lines.append(note)

def create_watchlist_message(
    watchlist: pd.DataFrame,
    market_status: dict[str, object],
) -> str:
    capital_text = (
        f"₹{ACCOUNT_CAPITAL:,.0f}"
    )

    max_risk = (
        ACCOUNT_CAPITAL
        * RISK_PER_TRADE_PCT
        / 100
    )

    lines = [
        "MOMENTUM & BREAKOUT SCANNER V1.0",
        f"Universe: {STOCK_UNIVERSE_NAME}",
        (
            "Generated: "
            + datetime.now().strftime(
                "%d %b %Y, %I:%M %p"
            )
        ),
        (
            "Market: "
            + str(
                market_status[
                    "Market Status"
                ]
            )
        ),
        (
            "Distribution days: "
            f"{int(market_status.get('Distribution Days', 0))}/"
            f"{int(market_status.get('Distribution Lookback', 25))} | "
            f"Pressure: {market_status.get('Distribution Pressure', 'N/A')} | "
            f"Volume: {market_status.get('Distribution Volume Source', 'N/A')}"
        ),
        (
            f"Capital: {capital_text} | "
            f"Maximum planned risk/trade: "
            f"₹{max_risk:,.0f}"
        ),
        "",
    ]

    if watchlist.empty:
        lines.append(
            "No stocks met the final criteria."
        )
        return "\n".join(
            lines
        )

    lines.extend(
        _summary_lines(
            watchlist
        )
    )
    lines.append(
        (
            "Eligible candidates: "
            f"{int(watchlist.attrs.get('eligible_count', len(watchlist)))}"
            " | Telegram displays: "
            f"{int(watchlist.attrs.get('displayed_count', len(watchlist)))}"
        )
    )

    best = watchlist.iloc[0]

    lines.extend(
        [
            "",
            "⭐ TODAY'S BEST OPPORTUNITY",
            (
                f"{best['Symbol']} | "
                f"{_action_icon(str(best['Action']))} "
                f"{best['Action']}"
            ),
            (
                f"Confidence "
                f"{_confidence_value(best):.1f}% | "
                f"Entry Status "
                f"{best['Entry Status']}"
            ),
            "",
        ]
    )

    for _, row in (
        watchlist.iterrows()
    ):
        action = str(
            row[
                "Action"
            ]
        )

        lines.extend(
            [
                (
                    f"{int(row['Watchlist Rank'])}. "
                    f"{row['Symbol']} | "
                    f"Grade "
                    f"{row['Trade Grade']}"
                ),
                (
                    f"Action: "
                    f"{_action_icon(action)} "
                    f"{action} | "
                    f"Confidence "
                    f"{_confidence_value(row):.1f}%"
                ),
                (
                    f"Current "
                    f"₹{row['Current Price']:.2f} | "
                    f"Entry "
                    f"₹{row['Suggested Entry']:.2f} | "
                    f"Live extension "
                    f"{row['Live Extension %']:+.2f}%"
                ),
                (
                    f"Entry Status: "
                    f"{row['Entry Status']}"
                ),
                (
                    f"Qualified by: "
                    f"{row.get('Qualified Scanner', 'Breakout Scanner')}"
                ),
                (
                    f"Breakout status: "
                    f"{row.get('Breakout Status', 'PATTERN SETUP')} | "
                    f"Score {float(row.get('Breakout Score', 0) or 0):.1f}/100"
                ),
                (
                    f"Daily move "
                    f"{float(row.get('Daily Gain %', 0) or 0):+.2f}% | "
                    f"5-day return "
                    f"{float(row.get('5D Return %', 0) or 0):+.2f}% | "
                    f"Historical volume "
                    f"{float(row.get('Historical Volume Ratio', 0) or 0):.2f}x"
                ),
                (
                    f"Pattern: "
                    f"{row.get('Primary Pattern', 'Breakout Watch')} | "
                    f"Confidence "
                    f"{float(row.get('Pattern Confidence', 0) or 0):.1f}%"
                ),
            ]
        )

        matched_patterns = str(
            row.get(
                "Matched Patterns",
                "",
            )
        ).strip()
        if matched_patterns and matched_patterns != "None":
            lines.append(
                f"Pattern confirmations: {matched_patterns}"
            )

        lines.append(
            (
                "Fundamentals: "
                f"{row.get('Fundamentals Gate Status', 'NOT LOADED')} | "
                f"EPS growth {_optional_percent(row.get('EPS Growth YoY %'))} | "
                f"Previous EPS {_optional_percent(row.get('Previous EPS Growth YoY %'))} | "
                f"Sales growth {_optional_percent(row.get('Sales Growth YoY %'))} | "
                f"Margin {_optional_percent(row.get('Operating Margin %'))}"
            )
        )
        lines.append(
            (
                f"RS Score: {float(row.get('RS Score', 0) or 0):.0f} | "
                f"RS line: {row.get('RS Line Status', 'UNAVAILABLE')} | "
                f"RS line new high: "
                f"{'YES' if bool(row.get('RS Line New High', False)) else 'NO'}"
                f" | Leads price: "
                f"{'YES' if bool(row.get('RS Line Leads Price', False)) else 'NO'}"
                f" | 20D slope: "
                f"{float(row.get('RS Line 20D Slope %', 0) or 0):+.2f}%"
            )
        )

        _append_trade_plan_lines(
            lines,
            row,
        )

        _append_circuit_lines(
            lines,
            row,
        )

        if SHOW_VOLUME_PANEL:
            _append_volume_lines(
                lines,
                row,
            )

        if SHOW_EMA_PANEL:
            alignment = (
                "BULLISH"
                if bool(
                    row.get(
                        "EMA Bullish Alignment",
                        False,
                    )
                )
                else "MIXED"
            )

            lines.extend(
                [
                    (
                        f"EMA 10 "
                        f"₹{row['EMA 10']:.2f} | "
                        f"EMA 20 "
                        f"₹{row['EMA 20']:.2f} | "
                        f"EMA 50 "
                        f"₹{row['EMA 50']:.2f}"
                    ),
                    (
                        f"EMA alignment: "
                        f"{alignment} | "
                        f"Urgency: "
                        f"{row.get('Trade Urgency', 'N/A')}"
                    ),
                ]
            )

        lines.extend(
            [
                (
                    f"Quality "
                    f"{row['Trade Quality Score']:.1f}/100 | "
                    f"RS "
                    f"{row['RS Score']:.0f} | "
                    f"Sector "
                    f"{row['Sector RS Score']:.0f} | "
                    f"Volume "
                    f"{row['Volume Score']:.0f} | "
                    f"VCP "
                    f"{row['VCP Score']:.0f}"
                ),
                (
                    f"Priority Score "
                    f"{row['Priority Score']:.1f}/100"
                ),
                (
                    f"Decision: "
                    f"{row['Decision Reason']}"
                ),
                (
                    f"Why: "
                    f"{row['Why Selected']}"
                ),
                "",
            ]
        )

    lines.append(
        "Screening and planning output only. "
        "BUY NOW means configured price, quality and "
        "volume rules are met. Confirm chart, liquidity, "
        "news and actual order risk."
    )

    return "\n".join(
        lines
    )


def save_watchlist_message(
    message: str,
    output_file: Path,
) -> None:
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file.write_text(
        message,
        encoding="utf-8",
    )
