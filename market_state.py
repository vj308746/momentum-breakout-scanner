from __future__ import annotations

import threading
import time
from copy import deepcopy
from typing import Any

import pandas as pd

from instrument_mapper import UpstoxInstrumentMapper
from upstox_client import UpstoxClient
from upstox_market_stream import UpstoxMarketStream


class LiveMarketState:
    """Process-level market state shared by all Streamlit sessions.

    REST is used only to warm a symbol's minute history. After warm-up,
    Upstox V3 WebSocket ticks update the current minute in memory. UI reruns
    only read this state; they do not create sockets or poll REST endpoints.
    """

    def __init__(self, client: UpstoxClient | None = None, mapper: UpstoxInstrumentMapper | None = None) -> None:
        self.client = client or UpstoxClient()
        self.mapper = mapper or UpstoxInstrumentMapper()
        self.stream = UpstoxMarketStream(self.client.access_token)
        self._lock = threading.RLock()
        self._history: dict[str, pd.DataFrame] = {}
        self._history_loaded_at: dict[str, float] = {}
        self._symbols: dict[str, str] = {}
        self._last_warmup_error: dict[str, str] = {}
        self._subscription_errors: dict[str, str] = {}

    def start(self) -> None:
        self.stream.start()

    def subscribe(self, symbols: list[str]) -> None:
        keys: list[str] = []
        errors: dict[str, str] = {}
        for symbol in symbols:
            symbol = str(symbol).strip().upper()
            if not symbol:
                continue
            try:
                key = self.mapper.resolve(symbol)
                self._symbols[symbol] = key
                keys.append(key)
            except Exception as exc:
                errors[symbol] = str(exc)

        with self._lock:
            self._subscription_errors.update(errors)

        if keys:
            self.stream.set_instruments(sorted(set(self._symbols.values())))
            self.stream.start()

    def status(self) -> dict[str, Any]:
        return {
            "connected": self.stream.connected,
            "last_error": self.stream.last_error,
            "last_message_at": self.stream.last_message_at,
            "last_live_message_at": self.stream.last_live_message_at,
            "requested": self.stream.requested_count,
            "subscribed": self.stream.subscribed_count,
            "live": self.stream.live_count,
            "subscription_errors": len(self._subscription_errors),
        }

    def snapshot(self, symbol: str) -> dict[str, Any]:
        key = self.mapper.resolve(symbol)
        return self.stream.snapshot().get(key, {})

    def _warmup(self, symbol: str) -> pd.DataFrame:
        key = self.mapper.resolve(symbol)
        now = time.time()
        with self._lock:
            existing = self._history.get(key)
            loaded = self._history_loaded_at.get(key, 0)
            if existing is not None and now - loaded < 600:
                return existing.copy()

        raw = self.client.get_intraday_candles(key, "minutes", 1)
        from live_data import candles_to_dataframe
        frame = candles_to_dataframe(raw)
        with self._lock:
            self._history[key] = frame.copy()
            self._history_loaded_at[key] = now
            self._last_warmup_error.pop(key, None)
        return frame

    def minute_frame(self, symbol: str) -> pd.DataFrame:
        key = self.mapper.resolve(symbol)
        frame = self._warmup(symbol)
        snap = self.stream.snapshot().get(key, {})
        i1 = snap.get("i1")
        if i1 and i1.get("ts"):
            ts = pd.to_datetime(int(i1["ts"]), unit="ms", utc=True)
            row = pd.DataFrame([{
                "Date": ts,
                "Open": i1.get("open"),
                "High": i1.get("high"),
                "Low": i1.get("low"),
                "Close": i1.get("close"),
                "Volume": i1.get("volume", 0),
                "Open Interest": 0,
            }]).set_index("Date")
            frame = pd.concat([frame.drop(index=frame.index[-1], errors="ignore"), row])
            frame = frame[~frame.index.duplicated(keep="last")].sort_index()
            with self._lock:
                self._history[key] = frame.tail(5000).copy()
        return frame.tail(5000)

    @staticmethod
    def aggregate(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        rules = {"5m": "5min", "15m": "15min", "30m": "30min", "1H": "1h"}
        rule = rules.get(timeframe)
        if not rule:
            return frame
        agg = frame[["Open", "High", "Low", "Close", "Volume"]].resample(
            rule, origin="start_day", offset="15min"
        ).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
        return agg.dropna(subset=["Open", "High", "Low", "Close"]).tail(500)

    def candles(self, symbol: str, timeframe: str) -> pd.DataFrame:
        return self.aggregate(self.minute_frame(symbol), timeframe)
