from __future__ import annotations

import threading
import time
from typing import Any

import pandas as pd

from confirmation_engine import enrich
from realtime_scanner import RealTimeBreakoutScanner, ScannerConfig


class LiveScannerService:
    """Background scanner that continuously evaluates live WebSocket state.

    Streamlit sessions only read the latest snapshot. The scanner therefore
    continues working even while a browser is not actively rerunning.
    """

    def __init__(self, live, interval_seconds: float = 3.0) -> None:
        self.live = live
        self.scanner = RealTimeBreakoutScanner(live)
        self.interval_seconds = max(1.0, float(interval_seconds))
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._report = pd.DataFrame()
        self._config = ScannerConfig()
        self._results = pd.DataFrame()
        self._last_scan_at = 0.0
        self._last_error = ""
        self._scan_count = 0
        self._scan_started_at = 0.0
        self._scan_in_progress = False
        self._scan_duration_seconds = 0.0

    def configure(self, report: pd.DataFrame, config: ScannerConfig) -> None:
        report_copy = report.copy() if report is not None else pd.DataFrame()
        # Subscribe first so the UI can observe a live universe immediately.
        # Historical REST warm-up happens in the background scanner afterwards.
        try:
            self.scanner.prepare_universe(report_copy, config)
        except Exception as exc:
            with self._lock:
                self._last_error = f"Universe preparation failed: {exc}"
        with self._lock:
            self._report = report_copy
            self._config = config
        self.start()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="live-breakout-scanner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.time()
            with self._lock:
                report = self._report.copy()
                config = self._config
            with self._lock:
                self._scan_started_at = started
                self._scan_in_progress = True
            try:
                result = self.scanner.scan(report, config)
                result = enrich(result)
                with self._lock:
                    self._results = result
                    self._last_error = ""
                    self._last_scan_at = time.time()
                    self._scan_count += 1
                    self._scan_duration_seconds = time.time() - started
            except Exception as exc:
                with self._lock:
                    self._last_error = str(exc)
                    self._last_scan_at = time.time()
            finally:
                with self._lock:
                    self._scan_in_progress = False
            elapsed = time.time() - started
            self._stop.wait(max(0.25, self.interval_seconds - elapsed))

    def snapshot(self) -> pd.DataFrame:
        with self._lock:
            return self._results.copy()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": bool(self._thread and self._thread.is_alive()),
                "last_scan_at": self._last_scan_at,
                "last_error": self._last_error,
                "scan_count": self._scan_count,
                "symbols": len(self._results),
                "scan_in_progress": self._scan_in_progress,
                "scan_started_at": self._scan_started_at,
                "scan_duration_seconds": self._scan_duration_seconds,
            }
