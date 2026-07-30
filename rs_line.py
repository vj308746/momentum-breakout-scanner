from __future__ import annotations

import numpy as np
import pandas as pd

from config import (
    RS_LINE_LOOKBACK_DAYS,
    RS_LINE_SLOPE_DAYS,
)


def calculate_rs_line_metrics(
    stock_data: pd.DataFrame,
    benchmark_data: pd.DataFrame,
) -> dict[str, object]:
    aligned = pd.concat(
        [
            pd.to_numeric(
                stock_data["Close"],
                errors="coerce",
            ).rename("stock"),
            pd.to_numeric(
                benchmark_data["Close"],
                errors="coerce",
            ).rename("benchmark"),
        ],
        axis=1,
        join="inner",
    ).dropna()
    aligned = aligned[aligned["benchmark"] > 0]
    if len(aligned) < RS_LINE_SLOPE_DAYS + 2:
        return {
            "RS Line Data Available": False,
            "RS Line Status": "UNAVAILABLE - INSUFFICIENT ALIGNED HISTORY",
            "RS Line New High": False,
            "RS Line Leads Price": False,
            "RS Line 20D Slope %": 0.0,
        }
    ratio = aligned["stock"] / aligned["benchmark"]
    prior = ratio.iloc[:-1].tail(RS_LINE_LOOKBACK_DAYS)
    rs_new_high = bool(
        len(prior) > 0
        and ratio.iloc[-1] >= prior.max()
    )
    prior_price = (
        aligned["stock"].iloc[:-1]
        .tail(RS_LINE_LOOKBACK_DAYS)
    )
    price_new_high = bool(
        len(prior_price) > 0
        and aligned["stock"].iloc[-1]
        >= prior_price.max()
    )
    recent = ratio.tail(RS_LINE_SLOPE_DAYS)
    slope = float(
        np.polyfit(
            np.arange(len(recent), dtype=float),
            recent.to_numpy(dtype=float),
            1,
        )[0]
    )
    slope_pct = (
        slope / float(recent.mean()) * 100
        if float(recent.mean()) != 0
        else 0.0
    )
    return {
        "RS Line Data Available": True,
        "RS Line Status": "AVAILABLE",
        "RS Line New High": rs_new_high,
        "RS Line Leads Price": (
            rs_new_high and not price_new_high
        ),
        "RS Line 20D Slope %": round(
            slope_pct,
            3,
        ),
    }
