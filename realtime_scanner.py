from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import pandas as pd

from config import STOCK_UNIVERSE_CSV_URL
from live_breakout_engine import evaluate_breakout, state_to_dict
from live_data import LiveUpstoxData


@dataclass(frozen=True)
class ScannerConfig:
    max_symbols: int = 100
    timeframe: str = "5m"
    include_below_resistance: bool = False
    warmup_workers: int = 4


class RealTimeBreakoutScanner:
    """Continuously evaluates the configured live candidate universe.

    The scanner deliberately reuses the existing breakout engine. Candidate
    selection is cheap; candle retrieval comes from the persistent Phase-3
    market state, so the UI does not create REST requests per refresh.
    """

    def __init__(self, live: LiveUpstoxData) -> None:
        self.live = live

    @staticmethod
    def _candidate_frame(report: pd.DataFrame, include_below: bool) -> pd.DataFrame:
        if report is None or report.empty or "Symbol" not in report.columns:
            return pd.DataFrame(columns=["Symbol"])
        frame = report.copy()
        frame["Symbol"] = frame["Symbol"].astype(str).str.upper().str.strip()
        frame = frame[frame["Symbol"].ne("")].drop_duplicates("Symbol")
        if not include_below and "Action" in frame.columns:
            preferred = {"BUY NOW", "WATCH", "BUY ON BREAKOUT", "BREAKOUT / VOLUME PENDING"}
            filtered = frame[frame["Action"].astype(str).isin(preferred)]
            if not filtered.empty:
                frame = filtered
        if "Trade Quality Score" in frame.columns:
            frame["_rank"] = pd.to_numeric(frame["Trade Quality Score"], errors="coerce").fillna(-1)
            frame = frame.sort_values("_rank", ascending=False)
        return frame

    def load_fallback_universe(self, limit: int) -> pd.DataFrame:
        # Prefer the already-loaded Upstox instrument master. This avoids
        # blocking the background scanner on the external Nifty Indices CSV,
        # which is not required for live streaming.
        try:
            frame = self.live.mapper.instruments.copy()
            if "trading_symbol" in frame.columns:
                if "segment" in frame.columns:
                    frame = frame[frame["segment"].astype(str).str.upper().eq("NSE_EQ")]
                if "instrument_type" in frame.columns:
                    preferred = frame[
                        frame["instrument_type"].astype(str).str.upper().isin({"EQ", "EQUITY"})
                    ]
                    if not preferred.empty:
                        frame = preferred
                symbols = (
                    frame["trading_symbol"]
                    .astype(str)
                    .str.upper()
                    .str.strip()
                )
                out = pd.DataFrame({"Symbol": symbols})
                out = out[out["Symbol"].ne("")].drop_duplicates()
                if not out.empty:
                    return out.head(limit)
        except Exception:
            pass

        # Secondary fallback for environments where the mapper master is
        # unavailable. Keep this as a last resort because the external CSV
        # can be slow or blocked by the hosting environment.
        try:
            frame = pd.read_csv(STOCK_UNIVERSE_CSV_URL)
            symbol_col = next(
                (c for c in frame.columns if str(c).strip().lower() in {"symbol", "ticker"}),
                None,
            )
            if symbol_col is not None:
                out = pd.DataFrame({
                    "Symbol": frame[symbol_col].astype(str).str.upper().str.strip()
                })
                return out[out["Symbol"].ne("")].drop_duplicates().head(limit)
        except Exception:
            pass
        return pd.DataFrame(columns=["Symbol"])

    def prepare_universe(self, report: pd.DataFrame, config: ScannerConfig) -> list[str]:
        """Resolve and subscribe the live universe before historical warm-up starts."""
        candidate = self._candidate_frame(report, config.include_below_resistance)
        if candidate.empty:
            candidate = self.load_fallback_universe(config.max_symbols)
        if candidate.empty or "Symbol" not in candidate.columns:
            return []
        symbols = (
            candidate["Symbol"]
            .astype(str)
            .str.strip()
            .str.upper()
            .replace("", pd.NA)
            .dropna()
            .drop_duplicates()
            .head(config.max_symbols)
            .tolist()
        )
        if symbols:
            self.live.start_stream(symbols)
        return symbols

    def scan(self, report: pd.DataFrame, config: ScannerConfig) -> pd.DataFrame:
        candidate = self._candidate_frame(report, config.include_below_resistance)
        if candidate.empty:
            candidate = self.load_fallback_universe(config.max_symbols)
        candidate = candidate.head(config.max_symbols).copy()
        symbols = candidate["Symbol"].tolist()
        self.live.start_stream(symbols)

        report_by_symbol = candidate.set_index("Symbol", drop=False).to_dict("index") if not candidate.empty else {}

        def evaluate_symbol(symbol: str) -> dict[str, Any]:
            try:
                candles = self.live.live_candles(symbol, config.timeframe)
                result = evaluate_breakout(candles)
                row = {"Symbol": symbol, **state_to_dict(result)}
                row["CMP"] = float(candles["Close"].iloc[-1])
                row["Candle Time"] = candles.index[-1]
                meta = report_by_symbol.get(symbol, {})
                for key in (
                    "Trade Quality Score", "Confidence Score", "RS Score", "Sector RS Score",
                    "Volume Score", "VCP Score", "Trend Template Pass", "Primary Pattern",
                    "Action", "Trade Grade", "Pivot Resistance", "Pattern Confidence",
                ):
                    if key in meta:
                        row[key] = meta[key]
                return row
            except Exception as exc:
                return {"Symbol": symbol, "State": "DATA ERROR", "Reason": str(exc)}

        workers = max(1, min(int(config.warmup_workers), max(1, len(symbols))))
        if workers == 1:
            rows = [evaluate_symbol(symbol) for symbol in symbols]
        else:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="live-warmup") as pool:
                futures = {pool.submit(evaluate_symbol, symbol): symbol for symbol in symbols}
                completed: dict[str, dict[str, Any]] = {}
                for future in as_completed(futures):
                    symbol = futures[future]
                    try:
                        completed[symbol] = future.result()
                    except Exception as exc:
                        completed[symbol] = {"Symbol": symbol, "State": "DATA ERROR", "Reason": str(exc)}
                rows = [completed[symbol] for symbol in symbols]
        return pd.DataFrame(rows)
