# Phase 1 + Phase 2 deployment

## Streamlit app

Main entry point:

```bash
streamlit run live_terminal.py
```

Configure the Upstox access token in the hosting platform's Streamlit Secrets:

```toml
UPSTOX_ACCESS_TOKEN = "YOUR_TOKEN"
```

The same variable can still be supplied as an environment variable for GitHub Actions/local execution.

## Phase 2 live stream

The terminal uses Upstox Market Data Feed V3 over WebSocket for intraday updates. Historical REST candles are used as the warm-up; the WebSocket supplies the current 1-minute candle, which is aggregated to 5m/15m/30m/1H.

The WebSocket layer is read-only and does not place orders.

## Existing scanner

Keep the existing GitHub Actions workflow unchanged. It continues to run `main.py` and Telegram alerts separately from the Streamlit terminal.
