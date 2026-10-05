from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from instrument_mapper import UpstoxInstrumentMapper
from market_state import LiveMarketState
from upstox_client import UpstoxClient

TIMEFRAMES = {
    "5m": ("intraday", "minutes", 5),
    "15m": ("intraday", "minutes", 15),
    "30m": ("intraday", "minutes", 30),
    "1H": ("intraday", "hours", 1),
    "Daily": ("historical", "days", 1),
    "Weekly": ("historical", "weeks", 1),
}


def candles_to_dataframe(candles: list[list[Any]]) -> pd.DataFrame:
    rows = [c[:7] for c in candles if isinstance(c, list) and len(c) >= 6]
    if not rows:
        raise RuntimeError("No candle data returned by Upstox.")
    for row in rows:
        while len(row) < 7:
            row.append(0)
    frame = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume", "Open Interest"])
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", utc=True)
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
    return frame.dropna(subset=["Date", "Open", "High", "Low", "Close", "Volume"]).sort_values("Date").drop_duplicates("Date", keep="last").set_index("Date")


class LiveUpstoxData:
    """Compatibility facade over the process-level LiveMarketState."""

    def __init__(self, client: UpstoxClient | None = None, mapper: UpstoxInstrumentMapper | None = None, stream=None, state: LiveMarketState | None = None) -> None:
        self.client = client or UpstoxClient()
        self.mapper = mapper or UpstoxInstrumentMapper()
        self.state = state or LiveMarketState(self.client, self.mapper)
        self.stream = self.state.stream

    def resolve(self, symbol: str) -> str:
        return self.mapper.resolve(symbol)

    def ltp(self, symbol: str) -> float | None:
        snap = self.stream_snapshot(symbol)
        if snap.get("ltp") is not None:
            return float(snap["ltp"])
        key = self.resolve(symbol)
        data = self.client.get_ltp([key])
        quote = data.get(key) or next(iter(data.values()), None)
        if not isinstance(quote, dict):
            return None
        for field in ("last_price", "ltp", "lastPrice"):
            if field in quote:
                return float(quote[field])
        return None

    def start_stream(self, symbols: list[str]) -> None:
        self.state.subscribe(symbols)

    def stream_snapshot(self, symbol: str) -> dict[str, Any]:
        return self.state.snapshot(symbol)

    @staticmethod
    def _aggregate_minute(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        return LiveMarketState.aggregate(frame, timeframe)

    def live_candles(self, symbol: str, timeframe: str, days: int = 30) -> pd.DataFrame:
        if timeframe in {"5m", "15m", "30m", "1H"}:
            return self.state.candles(symbol, timeframe)
        return self.candles(symbol, timeframe, days)

    def candles(self, symbol: str, timeframe: str, days: int = 30) -> pd.DataFrame:
        key = self.resolve(symbol)
        mode, unit, interval = TIMEFRAMES[timeframe]
        if mode == "intraday":
            raw = self.client.get_intraday_candles(key, unit, interval)
        else:
            end = date.today()
            start = end - timedelta(days=days)
            raw = self.client.get_historical_candles(key, unit, interval, end, start)
        return candles_to_dataframe(raw)
