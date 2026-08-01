from __future__ import annotations

import pandas as pd

from config import (
    MIN_AVG_TURNOVER_VALUE,
    MIN_PRICE,
)


def add_liquidity_gate(
    report: pd.DataFrame,
) -> pd.DataFrame:
    """Apply hard price and average-turnover eligibility rules."""

    frame = report.copy()
    price = pd.to_numeric(
        frame.get(
            "Current Price",
            pd.Series(float("nan"), index=frame.index),
        ),
        errors="coerce",
    )
    average_volume = pd.to_numeric(
        frame.get(
            "20D Avg Volume",
            pd.Series(float("nan"), index=frame.index),
        ),
        errors="coerce",
    )

    average_turnover = price * average_volume
    price_pass = price.ge(MIN_PRICE)
    turnover_pass = average_turnover.ge(
        MIN_AVG_TURNOVER_VALUE
    )

    frame["20D Avg Turnover Value"] = average_turnover.round(0)
    frame["Minimum Price Pass"] = price_pass.fillna(False)
    frame["Minimum Turnover Pass"] = turnover_pass.fillna(False)
    frame["Liquidity Eligible"] = (
        frame["Minimum Price Pass"]
        & frame["Minimum Turnover Pass"]
    )

    frame["Liquidity Status"] = "PASS"
    frame.loc[
        ~frame["Minimum Price Pass"],
        "Liquidity Status",
    ] = "FAIL - PRICE"
    frame.loc[
        frame["Minimum Price Pass"]
        & ~frame["Minimum Turnover Pass"],
        "Liquidity Status",
    ] = "FAIL - TURNOVER"

    return frame
