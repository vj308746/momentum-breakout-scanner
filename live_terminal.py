from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from confirmation_engine import enrich
from config import (
    LIVE_SCANNER_MAX_SYMBOLS,
    LIVE_SCANNER_STALE_SECONDS,
    LIVE_SCANNER_TIMEFRAME,
    LIVE_SCANNER_WARMUP_WORKERS,
    OUTPUT_FILE,
    UPSTOX_ACCESS_TOKEN,
)
from live_data import LiveUpstoxData, TIMEFRAMES
from live_scanner_service import LiveScannerService
from production_monitor import snapshot as health_snapshot
from realtime_scanner import ScannerConfig
from upstox_client import UpstoxAPIError, UpstoxAuthenticationError
from live_breakout_engine import evaluate_breakout

st.set_page_config(page_title="Momentum Breakout Terminal", layout="wide", initial_sidebar_state="expanded")


def money(value: Any) -> str:
    try:
        return f"₹{float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


@st.cache_data(show_spinner=False, ttl=30)
def load_report(path: str, modified: float) -> dict[str, pd.DataFrame]:
    del modified
    return pd.read_excel(path, sheet_name=None)


@st.cache_resource(show_spinner=False)
def get_live_data() -> LiveUpstoxData:
    live = LiveUpstoxData()
    live.state.start()
    return live


@st.cache_resource(show_spinner=False)
def get_scanner_service(_live: LiveUpstoxData) -> LiveScannerService:
    return LiveScannerService(_live, interval_seconds=3.0)


report_path = Path(OUTPUT_FILE)
workbook: dict[str, pd.DataFrame] = {}
if report_path.exists():
    workbook = load_report(str(report_path), report_path.stat().st_mtime)
all_stocks = workbook.get("All Stocks", pd.DataFrame()).copy()

with st.sidebar:
    st.header("Momentum Terminal")
    st.caption("Phase 4–8 architecture")
    st.success("Upstox token detected") if UPSTOX_ACCESS_TOKEN else st.warning("UPSTOX_ACCESS_TOKEN is not configured")
    page = st.radio("View", ["Market Scanner", "Stock Detail", "System Health"], index=0)
    st.divider()
    timeframe = st.selectbox("Scanner timeframe", ["5m", "15m", "30m", "1H"], index=["5m", "15m", "30m", "1H"].index(LIVE_SCANNER_TIMEFRAME) if LIVE_SCANNER_TIMEFRAME in {"5m", "15m", "30m", "1H"} else 0)
    max_symbols = st.slider("Live universe", 20, min(500, max(20, LIVE_SCANNER_MAX_SYMBOLS * 2)), LIVE_SCANNER_MAX_SYMBOLS, 10)
    include_below = st.checkbox("Include below-resistance candidates", value=False)
    auto_refresh = st.checkbox("Auto-refresh (2s)", value=True)
    if st.button("Clear cached report", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

if auto_refresh:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=2_000, key="phase4_terminal_refresh")
    except ImportError:
        pass

live = get_live_data()
service = get_scanner_service(live)
service.configure(
    all_stocks,
    ScannerConfig(
        max_symbols=max_symbols,
        timeframe=timeframe,
        include_below_resistance=include_below,
        warmup_workers=LIVE_SCANNER_WARMUP_WORKERS,
    ),
)

health = health_snapshot(live.state, stale_after_seconds=LIVE_SCANNER_STALE_SECONDS)

# Header/status strip.
h1, h2, h3, h4, h5, h6 = st.columns(6)
h1.metric("Feed", "LIVE" if health.connected and not health.stale else "DEGRADED")
h2.metric("Requested", health.requested)
h3.metric("Live", health.live)
h4.metric("Last live tick", f"{health.last_message_age_seconds:.1f}s" if health.last_message_age_seconds is not None else "—")
svc_status = service.status()
h5.metric("Scan cycles", svc_status["scan_count"])
h6.metric("Live rows", svc_status["symbols"])

if page == "Market Scanner":
    st.title("Momentum Breakout Terminal")
    st.caption("Real-time WebSocket scanner → advanced confirmation → ranked live dashboard. Existing pattern engine remains unchanged.")
    if not all_stocks.empty:
        st.info(f"Daily scanner report is being used to prioritize the live universe. Up to {max_symbols} symbols are streamed continuously.")
    else:
        st.warning("Daily report is unavailable. The terminal is using the local Upstox NSE instrument universe.")
    if service.status()["last_error"]:
        st.error(f"Scanner: {service.status()['last_error']}")

    df = service.snapshot()
    if df.empty:
        st.info("Waiting for the first live scan cycle. Historical warm-up can take longer on the first run.")
        st.stop()

    states = ["STRONG BREAKOUT", "CONFIRMED BREAKOUT", "RETEST HELD", "RETEST", "TESTING RESISTANCE", "NEAR RESISTANCE", "BELOW RESISTANCE", "FAILED BREAKOUT", "DATA ERROR"]
    state_filter = st.multiselect("State", states, default=["STRONG BREAKOUT", "CONFIRMED BREAKOUT", "RETEST HELD", "RETEST"])
    conf_filter = st.multiselect("Confirmation", ["CONFIRMED", "WATCH", "EARLY", "FAILED"], default=["CONFIRMED", "WATCH"])
    if state_filter:
        df = df[df["State"].isin(state_filter)]
    if conf_filter and "Confirmation Status" in df.columns:
        df = df[df["Confirmation Status"].isin(conf_filter)]
    if "Confirmation Score" in df.columns:
        df = df.sort_values(["Confirmation Score", "Volume Ratio"], ascending=[False, False])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Confirmed", int((df.get("Confirmation Status", pd.Series(dtype=str)) == "CONFIRMED").sum()))
    c2.metric("Strong Breakout", int((df.get("State", pd.Series(dtype=str)) == "STRONG BREAKOUT").sum()))
    c3.metric("Retest Held", int((df.get("State", pd.Series(dtype=str)) == "RETEST HELD").sum()))
    c4.metric("Data Errors", int((df.get("State", pd.Series(dtype=str)) == "DATA ERROR").sum()))

    display_cols = [
        "Symbol", "State", "Confirmation Status", "Confirmation Score", "CMP", "Resistance",
        "Distance To Resistance %", "Breakout %", "Volume Ratio", "Candle Confirmation",
        "RS Score", "Trend Template Pass", "Primary Pattern", "Trade Quality Score", "Reason",
    ]
    display = df[[c for c in display_cols if c in df.columns]].copy()
    for col in ["CMP", "Resistance"]:
        if col in display:
            display[col] = pd.to_numeric(display[col], errors="coerce").round(2)
    for col in ["Confirmation Score", "Distance To Resistance %", "Breakout %", "Volume Ratio", "RS Score", "Trade Quality Score"]:
        if col in display:
            display[col] = pd.to_numeric(display[col], errors="coerce").round(2)
    st.dataframe(display, use_container_width=True, hide_index=True, height=620)
    st.caption("Confirmation is an additive screening layer over the existing breakout engine. It does not change the underlying pattern rules or place orders.")

elif page == "Stock Detail":
    st.title("Live Stock Detail")
    source_symbols = all_stocks["Symbol"].dropna().astype(str).str.upper().drop_duplicates().tolist() if "Symbol" in all_stocks.columns else []
    search = st.text_input("NSE symbol", value=(source_symbols[0] if source_symbols else "RELIANCE")).strip().upper()
    symbol = search
    detail_tf = st.radio("Chart timeframe", list(TIMEFRAMES), horizontal=True, index=1)
    try:
        if detail_tf in {"5m", "15m", "30m", "1H"}:
            live.start_stream([symbol])
        candles = live.live_candles(symbol, detail_tf, days=120 if detail_tf in {"Daily", "Weekly"} else 30)
        snap = live.stream_snapshot(symbol)
        ltp = float(snap.get("ltp")) if snap.get("ltp") is not None else float(candles["Close"].iloc[-1])
        result = evaluate_breakout(candles)
        row = pd.Series({"State": result.state, "Volume Ratio": result.volume_ratio, "Candle Confirmation": result.candle_confirmation, "Breakout %": result.breakout_pct})
        confirmation = enrich(pd.DataFrame([row])).iloc[0]
    except (UpstoxAPIError, UpstoxAuthenticationError, RuntimeError, ValueError) as exc:
        st.error(str(exc))
        st.stop()

    a, b, c, d, e = st.columns(5)
    a.metric("CMP", money(ltp))
    b.metric("State", result.state)
    c.metric("Confirmation", confirmation["Confirmation Status"])
    d.metric("Confirmation Score", f"{confirmation['Confirmation Score']:.1f}")
    e.metric("Volume", f"{result.volume_ratio:.2f}x" if result.volume_ratio is not None else "—")
    st.write(f"**Reason:** {result.reason}")

    chart = make_subplots(specs=[[{"secondary_y": True}]])
    chart.add_trace(go.Candlestick(x=candles.index, open=candles["Open"], high=candles["High"], low=candles["Low"], close=candles["Close"], name="Price"), secondary_y=False)
    chart.add_trace(go.Bar(x=candles.index, y=candles["Volume"], name="Volume", opacity=0.25), secondary_y=True)
    if result.resistance:
        chart.add_hline(y=result.resistance, line_dash="dash", annotation_text="Resistance", secondary_y=False)
    chart.update_layout(height=680, xaxis_rangeslider_visible=False, legend=dict(orientation="h"), margin=dict(l=10, r=10, t=30, b=10))
    chart.update_yaxes(title_text="Price", secondary_y=False)
    chart.update_yaxes(title_text="Volume", secondary_y=True, showgrid=False)
    st.plotly_chart(chart, use_container_width=True)
    st.dataframe(pd.DataFrame([confirmation.to_dict()]), use_container_width=True, hide_index=True)

else:
    st.title("System Health & Monitoring")
    h = health_snapshot(live.state, stale_after_seconds=LIVE_SCANNER_STALE_SECONDS)
    s = service.status()
    cards = st.columns(6)
    cards[0].metric("WebSocket", "CONNECTED" if h.connected else "DISCONNECTED")
    cards[1].metric("Requested", h.requested)
    cards[2].metric("Live", h.live)
    cards[3].metric("Last live tick", f"{h.last_message_age_seconds:.1f}s" if h.last_message_age_seconds is not None else "—")
    cards[4].metric("Scanner", "RUNNING" if s["running"] else "STOPPED")
    cards[5].metric("Scan cycles", s["scan_count"])
    if h.stale:
        st.error("Market feed is stale or disconnected. The WebSocket service will reconnect automatically.")
    else:
        st.success("Market feed is healthy.")
    if h.requested and not h.live:
        st.warning(f"{h.requested} instruments are requested, but no live instrument data has been received yet.")
    if h.subscription_errors:
        st.warning(f"{h.subscription_errors} instrument mapping errors were skipped.")
    if h.last_error:
        st.warning(f"WebSocket last error: {h.last_error}")
    if s["last_error"]:
        st.warning(f"Scanner last error: {s['last_error']}")
    if s["scan_in_progress"]:
        st.info("Scanner is warming historical candles and evaluating the live universe in the background.")
    st.subheader("Architecture")
    st.code("Upstox V3 WebSocket → LiveMarketState → Background Scanner → Confirmation Engine → Streamlit UI", language="text")
    st.subheader("Operational notes")
    st.markdown("- WebSocket state is shared at process level.\n- UI reruns only read in-memory state.\n- REST is used for historical warm-up and Daily/Weekly charts.\n- Reconnects are automatic.\n- The terminal does not place orders or send alerts in this phase.")
