from __future__ import annotations

from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from config import (
    FUNDAMENTALS_CSV_PATH,
    FUNDAMENTALS_CSV_URL,
    FUNDAMENTALS_GATE_MODE,
    FUNDAMENTALS_MAX_AGE_DAYS,
    FUNDAMENTALS_MIN_EPS_GROWTH_PCT,
    FUNDAMENTALS_MIN_SALES_GROWTH_PCT,
    FUNDAMENTALS_REQUIRE_EPS_ACCELERATION,
    FUNDAMENTALS_REQUIRE_MARGIN_EXPANSION,
)


REQUIRED_COLUMNS = (
    "Symbol",
    "As Of Date",
    "EPS Growth YoY %",
    "Previous EPS Growth YoY %",
    "Sales Growth YoY %",
    "Operating Margin %",
    "Previous Operating Margin %",
)


def _normalise_fundamentals(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data.columns = [
        str(column).replace("\ufeff", "").strip()
        for column in data.columns
    ]
    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in data.columns
    ]
    if missing:
        raise RuntimeError(
            "Fundamentals data is missing columns: "
            + ", ".join(missing)
        )
    data["Symbol"] = (
        data["Symbol"].astype(str).str.strip().str.upper()
    )
    data["As Of Date"] = pd.to_datetime(
        data["As Of Date"],
        errors="coerce",
    )
    numeric = [
        column
        for column in REQUIRED_COLUMNS
        if column not in {"Symbol", "As Of Date"}
    ]
    for column in numeric:
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        )
    return (
        data.dropna(subset=["Symbol"])
        .sort_values("As Of Date")
        .drop_duplicates("Symbol", keep="last")
        .reset_index(drop=True)
    )


def load_fundamentals() -> pd.DataFrame:
    if FUNDAMENTALS_CSV_URL:
        response = requests.get(
            FUNDAMENTALS_CSV_URL,
            timeout=30,
        )
        response.raise_for_status()
        return _normalise_fundamentals(
            pd.read_csv(StringIO(response.text))
        )
    path = Path(FUNDAMENTALS_CSV_PATH)
    if not path.exists():
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    return _normalise_fundamentals(
        pd.read_csv(path)
    )


def add_fundamentals_gate(
    report: pd.DataFrame,
    fundamentals: pd.DataFrame,
) -> pd.DataFrame:
    frame = report.copy()
    source = fundamentals.copy()
    if source.empty:
        source = pd.DataFrame(columns=REQUIRED_COLUMNS)

    frame["Symbol"] = frame["Symbol"].astype(str).str.upper()
    frame = frame.merge(
        source,
        on="Symbol",
        how="left",
    )

    today = pd.Timestamp(date.today())
    age = (
        today - pd.to_datetime(
            frame["As Of Date"],
            errors="coerce",
        )
    ).dt.days
    frame["Fundamentals Data Available"] = (
        frame["As Of Date"].notna()
    )
    frame["Fundamentals Data Age Days"] = age
    frame["Fundamentals Fresh"] = (
        frame["Fundamentals Data Available"]
        & age.ge(0)
        & age.le(FUNDAMENTALS_MAX_AGE_DAYS)
    )
    frame["EPS Growth Pass"] = (
        pd.to_numeric(
            frame["EPS Growth YoY %"],
            errors="coerce",
        )
        >= FUNDAMENTALS_MIN_EPS_GROWTH_PCT
    )
    frame["Sales Growth Pass"] = (
        pd.to_numeric(
            frame["Sales Growth YoY %"],
            errors="coerce",
        )
        >= FUNDAMENTALS_MIN_SALES_GROWTH_PCT
    )
    frame["EPS Acceleration Pass"] = (
        pd.to_numeric(
            frame["EPS Growth YoY %"],
            errors="coerce",
        )
        >= pd.to_numeric(
            frame["Previous EPS Growth YoY %"],
            errors="coerce",
        )
    )
    frame["Margin Expansion Pass"] = (
        pd.to_numeric(
            frame["Operating Margin %"],
            errors="coerce",
        )
        >= pd.to_numeric(
            frame["Previous Operating Margin %"],
            errors="coerce",
        )
    )
    passes = (
        frame["Fundamentals Fresh"]
        & frame["EPS Growth Pass"]
        & frame["Sales Growth Pass"]
    )
    if FUNDAMENTALS_REQUIRE_EPS_ACCELERATION:
        passes &= frame["EPS Acceleration Pass"]
    if FUNDAMENTALS_REQUIRE_MARGIN_EXPANSION:
        passes &= frame["Margin Expansion Pass"]
    frame["Fundamentals Pass"] = passes

    required = FUNDAMENTALS_GATE_MODE == "required"
    frame["Fundamentals Eligible"] = (
        frame["Fundamentals Pass"]
        if required
        else True
    )
    frame["Fundamentals Gate Status"] = (
        "PASS"
    )
    frame.loc[
        ~frame["Fundamentals Data Available"],
        "Fundamentals Gate Status",
    ] = (
        "MISSING - BLOCKED"
        if required
        else "MISSING - ADVISORY"
    )
    frame.loc[
        frame["Fundamentals Data Available"]
        & ~frame["Fundamentals Pass"],
        "Fundamentals Gate Status",
    ] = (
        "FAIL - BLOCKED"
        if required
        else "FAIL - ADVISORY"
    )
    return frame
