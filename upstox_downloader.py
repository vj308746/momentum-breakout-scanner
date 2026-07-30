from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from config import (
    MIN_PRICE_HISTORY_RECORDS,
    UPSTOX_HISTORY_CALENDAR_DAYS,
    UPSTOX_HISTORY_INTERVAL,
    UPSTOX_HISTORY_UNIT,
    UPSTOX_INCLUDE_CURRENT_INTRADAY,
)
from instrument_mapper import (
    UpstoxInstrumentMapper,
)
from upstox_client import UpstoxClient


CANDLE_COLUMNS = [
    "Date",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "Open Interest",
]


class UpstoxHistoricalDownloader:
    """
    Converts Upstox V3 historical candles into the same
    pandas DataFrame shape used by the existing scanner.
    """

    def __init__(
        self,
        client: UpstoxClient | None = None,
        mapper: UpstoxInstrumentMapper | None = None,
    ) -> None:
        self.client = (
            client
            if client is not None
            else UpstoxClient()
        )

        self.mapper = (
            mapper
            if mapper is not None
            else UpstoxInstrumentMapper()
        )

    @staticmethod
    def candles_to_dataframe(
        candles: list[list[Any]],
    ) -> pd.DataFrame:
        if not candles:
            raise RuntimeError(
                "No Upstox historical candles returned."
            )

        valid_candles = [
            candle
            for candle in candles
            if isinstance(candle, list)
            and len(candle) >= 6
        ]

        if not valid_candles:
            raise RuntimeError(
                "Upstox returned no valid candle rows."
            )

        normalised_rows: list[list[Any]] = []

        for candle in valid_candles:
            row = list(candle[:7])

            if len(row) == 6:
                row.append(0)

            normalised_rows.append(row)

        dataframe = pd.DataFrame(
            normalised_rows,
            columns=CANDLE_COLUMNS,
        )

        dataframe["Date"] = pd.to_datetime(
            dataframe["Date"],
            errors="coerce",
            utc=True,
        )

        numeric_columns = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
            "Open Interest",
        ]

        for column in numeric_columns:
            dataframe[column] = pd.to_numeric(
                dataframe[column],
                errors="coerce",
            )

        dataframe = dataframe.dropna(
            subset=[
                "Date",
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
            ]
        )

        dataframe = (
            dataframe.sort_values("Date")
            .drop_duplicates(
                subset=["Date"],
                keep="last",
            )
            .set_index("Date")
        )

        return dataframe

    def download(
        self,
        symbol_or_key: str,
        calendar_days: int | None = None,
        to_date: date | None = None,
    ) -> pd.DataFrame:
        instrument_key = (
            self.mapper.resolve(
                symbol_or_key
            )
        )

        end_date = (
            to_date
            if to_date is not None
            else date.today()
        )

        history_days = (
            calendar_days
            if calendar_days is not None
            else UPSTOX_HISTORY_CALENDAR_DAYS
        )

        start_date = (
            end_date
            - timedelta(days=history_days)
        )

        candles = (
            self.client.get_historical_candles(
                instrument_key=instrument_key,
                unit=UPSTOX_HISTORY_UNIT,
                interval=(
                    UPSTOX_HISTORY_INTERVAL
                ),
                to_date=end_date,
                from_date=start_date,
            )
        )

        dataframe = (
            self.candles_to_dataframe(
                candles
            )
        )

        if not UPSTOX_INCLUDE_CURRENT_INTRADAY:
            today_utc = pd.Timestamp.now(
                tz="UTC"
            ).date()

            dataframe = dataframe[
                dataframe.index.date
                < today_utc
            ]

        if len(dataframe) < MIN_PRICE_HISTORY_RECORDS:
            raise RuntimeError(
                f"Insufficient Upstox history for "
                f"{symbol_or_key}: "
                f"{len(dataframe)} records"
            )

        return dataframe

    def download_ltp(
        self,
        symbols_or_keys: list[str],
    ) -> dict[str, Any]:
        instrument_keys = [
            self.mapper.resolve(value)
            for value in symbols_or_keys
        ]

        return self.client.get_ltp(
            instrument_keys
        )


_default_downloader: (
    UpstoxHistoricalDownloader | None
) = None


def get_upstox_downloader() -> (
    UpstoxHistoricalDownloader
):
    global _default_downloader

    if _default_downloader is None:
        _default_downloader = (
            UpstoxHistoricalDownloader()
        )

    return _default_downloader


def download_upstox_stock_data(
    symbol_or_key: str,
) -> pd.DataFrame:
    return get_upstox_downloader().download(
        symbol_or_key
    )
