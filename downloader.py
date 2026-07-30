from __future__ import annotations

import logging
from io import StringIO

import pandas as pd
import requests
import yfinance as yf

from config import (
    ALLOW_YAHOO_FALLBACK,
    DATA_SOURCE,
    DOWNLOAD_INTERVAL,
    DOWNLOAD_PERIOD,
    MAX_STOCKS,
    MIN_PRICE_HISTORY_RECORDS,
    STOCK_UNIVERSE_CSV_URL,
    STOCK_UNIVERSE_NAME,
)
from instrument_mapper import (
    UpstoxInstrumentMapper,
)
from upstox_downloader import (
    download_upstox_stock_data,
)


def _prepare_constituents(
    csv_text: str,
) -> pd.DataFrame:
    """Normalise an official NSE Indices constituent CSV."""
    constituents = pd.read_csv(
        StringIO(csv_text)
    )

    constituents.columns = [
        str(column)
        .replace("\ufeff", "")
        .strip()
        for column in constituents.columns
    ]

    required = [
        "Company Name",
        "Industry",
        "Symbol",
    ]

    missing = [
        column
        for column in required
        if column not in constituents.columns
    ]

    if missing:
        raise RuntimeError(
            "Official universe file is missing columns: "
            + ", ".join(missing)
        )

    for column in required:
        constituents[column] = (
            constituents[column]
            .astype(str)
            .str.strip()
        )

    constituents = constituents[
        constituents["Symbol"] != ""
    ].copy()

    constituents[
        "Yahoo Symbol"
    ] = constituents["Symbol"] + ".NS"
    constituents[
        "Universe Source"
    ] = STOCK_UNIVERSE_NAME

    return (
        constituents
        .drop_duplicates(
            subset=["Symbol"]
        )
        .sort_values("Symbol")
        .reset_index(drop=True)
    )


def load_stock_universe() -> pd.DataFrame:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/143 Safari/537.36"
        )
    }

    response = requests.get(
        STOCK_UNIVERSE_CSV_URL,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()

    constituents = _prepare_constituents(
        response.text
    )

    if DATA_SOURCE == "upstox":
        mapper = UpstoxInstrumentMapper()

        mapped, mapping_errors = (
            mapper.attach_instrument_keys(
                constituents
            )
        )

        if not mapping_errors.empty:
            logging.warning(
                "%s %s symbols could not "
                "be mapped to Upstox.",
                len(mapping_errors),
                STOCK_UNIVERSE_NAME,
            )

        constituents = mapped

    if MAX_STOCKS is not None:
        constituents = constituents.head(
            MAX_STOCKS
        ).copy()

    return constituents.reset_index(
        drop=True
    )


def load_nifty500_constituents() -> pd.DataFrame:
    """Backward-compatible alias retained for older integrations."""
    return load_stock_universe()


def _download_yahoo_data(
    symbol: str,
) -> pd.DataFrame:
    yahoo_symbol = (
        symbol
        if symbol.endswith(".NS")
        or symbol.startswith("^")
        else f"{symbol}.NS"
    )

    data = yf.download(
        yahoo_symbol,
        period=DOWNLOAD_PERIOD,
        interval=DOWNLOAD_INTERVAL,
        auto_adjust=True,
        progress=False,
        threads=False,
    )

    if data.empty:
        raise RuntimeError(
            "No Yahoo price data returned"
        )

    if isinstance(
        data.columns,
        pd.MultiIndex,
    ):
        data.columns = (
            data.columns
            .get_level_values(0)
        )

    required = [
        "Close",
        "High",
        "Low",
        "Volume",
    ]

    data = data.dropna(
        subset=required
    ).copy()

    if len(data) < MIN_PRICE_HISTORY_RECORDS:
        raise RuntimeError(
            f"Insufficient Yahoo history: "
            f"{len(data)} records"
        )

    return data


def download_stock_data(
    symbol: str,
    yahoo_fallback_symbol: str | None = None,
) -> pd.DataFrame:
    if DATA_SOURCE == "upstox":
        try:
            return (
                download_upstox_stock_data(
                    symbol
                )
            )
        except Exception:
            if not ALLOW_YAHOO_FALLBACK:
                raise

            logging.exception(
                "Upstox download failed for %s; "
                "using Yahoo fallback.",
                symbol,
            )

            return _download_yahoo_data(
                yahoo_fallback_symbol
                or symbol
            )

    if DATA_SOURCE == "yahoo":
        return _download_yahoo_data(
            symbol
        )

    raise RuntimeError(
        f"Unsupported DATA_SOURCE: "
        f"{DATA_SOURCE!r}"
    )
