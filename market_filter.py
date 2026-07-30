from __future__ import annotations

from typing import Any

import pandas as pd

from config import (
    DISTRIBUTION_CAUTION_COUNT,
    DISTRIBUTION_LOOKBACK_DAYS,
    DISTRIBUTION_MIN_DECLINE_PCT,
    DISTRIBUTION_PRESSURE_COUNT,
)


def calculate_market_status(
    data: pd.DataFrame,
    volume_data: pd.DataFrame | None = None,
) -> dict[str, Any]:
    data = data.copy()
    data["DMA_50"] = data["Close"].rolling(50).mean()
    data["DMA_200"] = data["Close"].rolling(200).mean()

    latest = data.iloc[-1]
    price = float(latest["Close"])
    dma_50 = float(latest["DMA_50"])
    dma_200 = float(latest["DMA_200"])
    dma_200_previous = float(data["DMA_200"].iloc[-21])

    bullish = (
        price > dma_50
        and price > dma_200
        and dma_50 > dma_200
        and dma_200 > dma_200_previous
    )

    distribution_frame = pd.DataFrame(
        {
            "Close": pd.to_numeric(
                data["Close"],
                errors="coerce",
            ),
        }
    )
    volume_source = "BENCHMARK"
    if (
        volume_data is not None
        and not volume_data.empty
        and "Volume" in volume_data.columns
    ):
        distribution_frame = distribution_frame.join(
            pd.to_numeric(
                volume_data["Volume"],
                errors="coerce",
            ).rename("Volume"),
            how="inner",
        )
        volume_source = "NIFTYBEES"
    else:
        distribution_frame["Volume"] = pd.to_numeric(
            data["Volume"],
            errors="coerce",
        )

    close_change = (
        distribution_frame["Close"]
        .pct_change()
        .mul(100)
    )
    distribution = (
        close_change.le(-DISTRIBUTION_MIN_DECLINE_PCT)
        & distribution_frame["Volume"].gt(
            distribution_frame["Volume"].shift(1)
        )
    )
    distribution_count = int(
        distribution.tail(
            DISTRIBUTION_LOOKBACK_DAYS
        ).sum()
    )
    if distribution_count >= DISTRIBUTION_PRESSURE_COUNT:
        market_status = "UNDER PRESSURE"
        bullish = False
    elif distribution_count >= DISTRIBUTION_CAUTION_COUNT:
        market_status = "CAUTIOUS"
        bullish = False
    else:
        market_status = (
            "BULLISH" if bullish else "CAUTIOUS"
        )

    return {
        "Market Price": round(price, 2),
        "Market 50 DMA": round(dma_50, 2),
        "Market 200 DMA": round(dma_200, 2),
        "Market Bullish": bullish,
        "Market Status": market_status,
        "Distribution Days": distribution_count,
        "Distribution Lookback": DISTRIBUTION_LOOKBACK_DAYS,
        "Distribution Pressure": (
            "HIGH"
            if distribution_count >= DISTRIBUTION_PRESSURE_COUNT
            else "ELEVATED"
            if distribution_count >= DISTRIBUTION_CAUTION_COUNT
            else "NORMAL"
        ),
        "Distribution Volume Source": volume_source,
    }
