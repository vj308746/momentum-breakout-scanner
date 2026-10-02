# Phases 4, 5, 6 and 8 — Production Live Terminal

Phase 7 (Trade Planner + Telegram Alerts) is intentionally skipped.

## Phase 4 — Real-time Breakout Scanner

`live_scanner_service.py` runs the scanner in a background daemon thread. The UI reads its latest snapshot instead of evaluating every symbol on each Streamlit rerun.

The scanner reuses the existing `live_breakout_engine.py` and the persistent Phase-3 WebSocket state. The daily `All Stocks` report is used to prioritize candidates; if unavailable, the configured Nifty Total Market CSV is used as a fallback.

## Phase 5 — Advanced Confirmation Engine

`confirmation_engine.py` adds a separate score based on:
- live breakout state
- volume expansion
- candle confirmation
- relative strength when present in the daily report
- trend-template pass when present
- extension beyond the breakout level

This is additive. Existing pattern logic is not rewritten.

## Phase 6 — Professional Terminal UI

The Streamlit application now has:
- Market Scanner
- Stock Detail
- System Health
- live feed status strip
- state and confirmation filters
- ranked scanner table
- live chart and resistance level
- operational status information

## Phase 8 — Reliability / Monitoring

`production_monitor.py` detects stale feed state and exposes:
- WebSocket connection status
- feed freshness
- subscription count
- scanner process status
- scan cycle count
- last WebSocket error
- last scanner error

The WebSocket reconnect behavior remains automatic. The terminal does not place orders or send alerts in this release.
