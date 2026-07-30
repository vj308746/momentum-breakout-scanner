from __future__ import annotations

from typing import Any

import pandas as pd


def analyse_stock(
    symbol: str,
    company_name: str,
    industry: str,
    data: pd.DataFrame,
) -> dict[str, Any]:
    data = data.copy()

    data["DMA_50"] = data["Close"].rolling(50).mean()
    data["DMA_150"] = data["Close"].rolling(150).mean()
    data["DMA_200"] = data["Close"].rolling(200).mean()
    data["DMA_20"] = data["Close"].rolling(20).mean()

    latest = data.iloc[-1]
    current_price = float(latest["Close"])
    dma_50 = float(latest["DMA_50"])
    dma_150 = float(latest["DMA_150"])
    dma_200 = float(latest["DMA_200"])
    dma_20 = float(latest["DMA_20"])

    last_252 = data.tail(252)
    high_52 = float(last_252["High"].max())
    low_52 = float(last_252["Low"].min())

    if low_52 <= 0 or high_52 <= 0:
        raise RuntimeError("Invalid 52-week high/low")

    above_low_pct = ((current_price - low_52) / low_52) * 100
    below_high_pct = ((high_52 - current_price) / high_52) * 100

    young_ipo = len(data) < 220
    if young_ipo:
        conditions = {
            "Price > 50 DMA": current_price > dma_50,
            "Price > 150 DMA": False,
            "Price > 200 DMA": False,
            "50 DMA > 150 DMA": False,
            "150 DMA > 200 DMA": False,
            "200 DMA Rising": False,
            "30% Above 52W Low": above_low_pct >= 20,
            "Within 25% of 52W High": below_high_pct <= 25,
        }
        ipo_conditions = {
            "Price > 20 DMA": current_price > dma_20,
            "Price > 50 DMA": current_price > dma_50,
            "20 DMA > 50 DMA": dma_20 > dma_50,
            "20% Above Listing Low": above_low_pct >= 20,
            "Within 25% of Listing High": below_high_pct <= 25,
        }
        trend_pass = all(ipo_conditions.values())
        passed = sum(bool(value) for value in ipo_conditions.values())
        total = len(ipo_conditions)
    else:
        dma_200_previous = float(data["DMA_200"].iloc[-21])
        if pd.isna(dma_200) or pd.isna(dma_200_previous):
            raise RuntimeError("Unable to calculate long-term moving averages")
        conditions = {
            "Price > 50 DMA": current_price > dma_50,
            "Price > 150 DMA": current_price > dma_150,
            "Price > 200 DMA": current_price > dma_200,
            "50 DMA > 150 DMA": dma_50 > dma_150,
            "150 DMA > 200 DMA": dma_150 > dma_200,
            "200 DMA Rising": dma_200 > dma_200_previous,
            "30% Above 52W Low": above_low_pct >= 30,
            "Within 25% of 52W High": below_high_pct <= 25,
        }
        ipo_conditions = {}
        trend_pass = all(conditions.values())
        passed = sum(bool(value) for value in conditions.values())
        total = len(conditions)

    return {
        "Symbol": symbol,
        "Company Name": company_name,
        "Industry": industry,
        "Current Price": round(current_price, 2),
        "50 DMA": round(dma_50, 2),
        "150 DMA": round(dma_150, 2) if not pd.isna(dma_150) else float("nan"),
        "200 DMA": round(dma_200, 2) if not pd.isna(dma_200) else float("nan"),
        "52W High": round(high_52, 2),
        "52W Low": round(low_52, 2),
        "% Above 52W Low": round(above_low_pct, 2),
        "% Below 52W High": round(below_high_pct, 2),
        **conditions,
        **ipo_conditions,
        "Trend Template Type": "IPO Adapted" if young_ipo else "Standard",
        "Conditions Passed": passed,
        "Total Conditions": total,
        "Score %": round((passed / total) * 100, 2),
        "Trend Template Pass": trend_pass,
    }
