from __future__ import annotations

import pandas as pd

from config import SECTOR_RS_THRESHOLD


def add_sector_strength(report: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    report = report.copy()

    sector_summary = (
        report.groupby("Industry", dropna=False)
        .agg(
            Sector_Stocks=("Symbol", "count"),
            Sector_3M_Return=("3M Return %", "median"),
            Sector_6M_Return=("6M Return %", "median"),
            Sector_12M_Return=("12M Return %", "median"),
        )
        .reset_index()
    )

    for period in ("3M", "6M", "12M"):
        sector_summary[f"Sector_{period}_Percentile"] = (
            sector_summary[f"Sector_{period}_Return"]
            .rank(method="average", pct=True)
            .mul(100)
        )

    sector_summary["Sector RS Score"] = (
        sector_summary["Sector_3M_Percentile"] * 0.40
        + sector_summary["Sector_6M_Percentile"] * 0.30
        + sector_summary["Sector_12M_Percentile"] * 0.30
    ).round(0).clip(1, 100)

    sector_summary["Sector RS Pass"] = (
        sector_summary["Sector RS Score"] >= SECTOR_RS_THRESHOLD
    )

    report = report.merge(
        sector_summary[
            ["Industry", "Sector RS Score", "Sector RS Pass"]
        ],
        on="Industry",
        how="left",
    )

    return report, sector_summary.sort_values(
        "Sector RS Score", ascending=False
    ).reset_index(drop=True)
