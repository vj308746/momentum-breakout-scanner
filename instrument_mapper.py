from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from config import (
    UPSTOX_INSTRUMENT_CACHE_FILE,
    UPSTOX_INSTRUMENT_CACHE_HOURS,
    UPSTOX_NSE_INSTRUMENTS_URL,
    UPSTOX_REQUEST_TIMEOUT_SECONDS,
)


INDEX_ALIASES: dict[str, str] = {
    "^NSEI": "NIFTY 50",
    "NIFTY": "NIFTY 50",
    "NIFTY50": "NIFTY 50",
    "NIFTY 50": "NIFTY 50",
    "^CNX500": "NIFTY 500",
    "NIFTY500": "NIFTY 500",
    "NIFTY 500": "NIFTY 500",
    "^NSEBANK": "NIFTY BANK",
    "BANKNIFTY": "NIFTY BANK",
    "NIFTY BANK": "NIFTY BANK",
    "INDIA VIX": "INDIA VIX",
}


class InstrumentMappingError(RuntimeError):
    """Raised when an NSE symbol cannot be mapped."""


def _cache_is_fresh(
    cache_file: Path,
) -> bool:
    if not cache_file.exists():
        return False

    modified_time = datetime.fromtimestamp(
        cache_file.stat().st_mtime,
        tz=timezone.utc,
    )

    age_hours = (
        datetime.now(timezone.utc)
        - modified_time
    ).total_seconds() / 3600

    return (
        age_hours
        <= UPSTOX_INSTRUMENT_CACHE_HOURS
    )


def _download_nse_instruments() -> list[dict[str, Any]]:
    response = requests.get(
        UPSTOX_NSE_INSTRUMENTS_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": (
                "MinerviniScanner/3.0"
            ),
        },
        timeout=UPSTOX_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    raw_content = response.content

    try:
        decoded = gzip.decompress(
            raw_content
        ).decode("utf-8")
    except OSError:
        # Some HTTP clients/servers may already decode gzip.
        decoded = raw_content.decode("utf-8")

    payload = json.loads(decoded)

    if not isinstance(payload, list):
        raise InstrumentMappingError(
            "Upstox instrument master is not a list."
        )

    return [
        item
        for item in payload
        if isinstance(item, dict)
    ]


def load_nse_instruments(
    force_refresh: bool = False,
) -> pd.DataFrame:
    cache_file = (
        UPSTOX_INSTRUMENT_CACHE_FILE
    )

    instruments: list[dict[str, Any]]

    if (
        not force_refresh
        and _cache_is_fresh(cache_file)
    ):
        instruments = json.loads(
            cache_file.read_text(
                encoding="utf-8"
            )
        )
    else:
        logging.info(
            "Downloading Upstox NSE instrument master"
        )
        instruments = (
            _download_nse_instruments()
        )

        cache_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        cache_file.write_text(
            json.dumps(
                instruments,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    dataframe = pd.DataFrame(instruments)

    if dataframe.empty:
        raise InstrumentMappingError(
            "Upstox NSE instrument master is empty."
        )

    required = {
        "instrument_key",
        "segment",
    }

    missing = required.difference(
        dataframe.columns
    )

    if missing:
        raise InstrumentMappingError(
            "Instrument master is missing fields: "
            + ", ".join(sorted(missing))
        )

    for column in (
        "instrument_key",
        "segment",
        "instrument_type",
        "trading_symbol",
        "name",
        "short_name",
    ):
        if column not in dataframe.columns:
            dataframe[column] = ""

        dataframe[column] = (
            dataframe[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    dataframe["_trading_symbol_norm"] = (
        dataframe["trading_symbol"]
        .str.upper()
    )

    dataframe["_name_norm"] = (
        dataframe["name"]
        .str.upper()
    )

    dataframe["_short_name_norm"] = (
        dataframe["short_name"]
        .str.upper()
    )

    return dataframe


class UpstoxInstrumentMapper:
    """
    Maps NSE equity symbols and index aliases to Upstox
    instrument keys using the official NSE JSON instrument file.
    """

    def __init__(
        self,
        instruments: pd.DataFrame | None = None,
    ) -> None:
        self.instruments = (
            instruments.copy()
            if instruments is not None
            else load_nse_instruments()
        )

    @staticmethod
    def _normalise_symbol(
        symbol: str,
    ) -> str:
        return (
            symbol.strip()
            .upper()
            .removesuffix(".NS")
        )

    def _equity_candidates(
        self,
        symbol: str,
    ) -> pd.DataFrame:
        normalised = self._normalise_symbol(
            symbol
        )

        frame = self.instruments

        candidates = frame[
            frame["segment"].str.upper().eq(
                "NSE_EQ"
            )
            & frame[
                "_trading_symbol_norm"
            ].eq(normalised)
        ].copy()

        if candidates.empty:
            return candidates

        # Prefer regular cash-equity records.
        preferred_types = {
            "EQ",
            "EQUITY",
        }

        candidates["_preferred"] = (
            candidates["instrument_type"]
            .str.upper()
            .isin(preferred_types)
        )

        return candidates.sort_values(
            by="_preferred",
            ascending=False,
        )

    def resolve_equity_symbol(
        self,
        symbol: str,
    ) -> str:
        candidates = self._equity_candidates(
            symbol
        )

        if candidates.empty:
            raise InstrumentMappingError(
                f"No Upstox NSE equity instrument "
                f"found for symbol {symbol!r}."
            )

        return str(
            candidates.iloc[0][
                "instrument_key"
            ]
        )

    def resolve_index(
        self,
        symbol_or_name: str,
    ) -> str:
        normalised = self._normalise_symbol(
            symbol_or_name
        )

        target_name = INDEX_ALIASES.get(
            normalised,
            normalised,
        )

        frame = self.instruments

        index_frame = frame[
            frame["segment"]
            .str.upper()
            .eq("NSE_INDEX")
        ].copy()

        exact_matches = index_frame[
            index_frame[
                "_trading_symbol_norm"
            ].eq(target_name)
            | index_frame[
                "_name_norm"
            ].eq(target_name)
            | index_frame[
                "_short_name_norm"
            ].eq(target_name)
        ]

        if exact_matches.empty:
            # Some versions of the master use title case or
            # additional spaces; use a conservative contains
            # match only after exact matching fails.
            contains_matches = index_frame[
                index_frame[
                    "_trading_symbol_norm"
                ].str.contains(
                    target_name,
                    regex=False,
                )
                | index_frame[
                    "_name_norm"
                ].str.contains(
                    target_name,
                    regex=False,
                )
            ]

            exact_matches = (
                contains_matches
            )

        if exact_matches.empty:
            raise InstrumentMappingError(
                f"No Upstox NSE index instrument "
                f"found for {symbol_or_name!r} "
                f"(normalised as {target_name!r})."
            )

        return str(
            exact_matches.iloc[0][
                "instrument_key"
            ]
        )

    def resolve(
        self,
        symbol_or_key: str,
    ) -> str:
        value = symbol_or_key.strip()

        if "|" in value:
            return value

        normalised = self._normalise_symbol(
            value
        )

        if (
            normalised in INDEX_ALIASES
            or value.startswith("^")
        ):
            return self.resolve_index(value)

        return self.resolve_equity_symbol(
            value
        )

    def attach_instrument_keys(
        self,
        constituents: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        if "Symbol" not in constituents.columns:
            raise InstrumentMappingError(
                "Constituent table is missing Symbol."
            )

        mapped_rows: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        for _, row in constituents.iterrows():
            symbol = str(row["Symbol"])

            try:
                instrument_key = (
                    self.resolve_equity_symbol(
                        symbol
                    )
                )

                mapped_row = row.to_dict()
                mapped_row[
                    "Upstox Instrument Key"
                ] = instrument_key

                mapped_rows.append(mapped_row)

            except Exception as exc:
                errors.append(
                    {
                        "Symbol": symbol,
                        "Mapping Error": str(exc),
                    }
                )

        mapped = pd.DataFrame(mapped_rows)
        error_frame = pd.DataFrame(errors)

        return mapped, error_frame
