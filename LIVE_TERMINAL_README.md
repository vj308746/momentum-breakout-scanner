# Live Momentum Breakout Terminal

## Run

1. Copy `.env.example` to `.env` and set `UPSTOX_ACCESS_TOKEN`.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Create/update the existing scanner report:

```powershell
python main.py
```

4. Start the terminal:

```powershell
streamlit run live_terminal.py
```

## Core logic

The terminal keeps the existing pattern engine and adds a live price-action state layer:

- Below Resistance
- Near Resistance
- Testing Resistance
- Confirmed Breakout
- Strong Breakout
- Retest
- Retest Held
- Failed Breakout

Core confirmation uses price level, candle behaviour and relative volume. Existing VCP, RS, Trend Template, Pocket Pivot/VDU, IPO Base and Episodic Pivot logic remains available in the project but is not required by the live state engine.

## Timeframes

- 5m
- 15m
- 30m
- 1H
- Daily
- Weekly

The Upstox V3 intraday candle API supports configurable minute/hour/day intervals, while the historical V3 API supports minutes, hours, days, weeks and months. The terminal uses those APIs rather than fabricating a live feed.

## Important

This is a read-only market-data terminal. It does not place orders. Entry, stop and target fields are mechanical reference calculations for analysis and must be validated with your own risk rules and backtesting before live use.
