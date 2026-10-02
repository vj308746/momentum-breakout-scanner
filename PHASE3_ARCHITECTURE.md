# Phase 3 — Persistent Live Terminal

The terminal now uses a process-level `LiveMarketState` shared by Streamlit sessions.

## Runtime flow

Browser rerun -> read in-memory market state -> breakout evaluation -> render.

The WebSocket and market state are created once through `st.cache_resource` and run in a daemon thread. REST is used only for historical minute warm-up (10-minute refresh per instrument) and for Daily/Weekly charts.

The V3 stream keeps the latest 1-minute candle in memory. The terminal aggregates that state into 5m, 15m, 30m and 1H candles without creating a REST request for every UI refresh.

## Important deployment boundary

This is persistent for the lifetime of the Streamlit application process. It is not a separate always-on trading daemon. If the hosting platform sleeps/restarts the process, the socket reconnects and the minute history is warmed again automatically.

## Upstox feed

The implementation uses Market Data Feed V3 `full` mode. Upstox documents V3 as the current WebSocket feed; V2 was discontinued after August 22, 2025.
