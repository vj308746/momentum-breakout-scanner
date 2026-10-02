# Phase 2 — Upstox WebSocket V3

The terminal now uses Upstox Market Data Feed V3 for intraday live updates.

## Flow

1. REST fetches recent 1-minute candles as the historical warm-up.
2. Upstox WebSocket V3 subscribes to the selected NSE instruments in `full` mode.
3. The live `I1` candle replaces the current 1-minute bar.
4. The terminal aggregates 1-minute bars into 5m / 15m / 30m / 1H candles.
5. The existing `live_breakout_engine.py` evaluates those candles without changing its rules.
6. The Streamlit UI refreshes to display the latest state.

## Security

The access token is read from `UPSTOX_ACCESS_TOKEN`, including Streamlit Secrets support from Phase 1. It is never hard-coded.

## Important

This phase adds real-time market-data streaming only. It does not place orders and does not change the scanner's Telegram workflow.
