# Momentum & Breakout Scanner

This is a standalone scanner for Indian breakout and momentum stocks. It is
intentionally separate from the Mark Minervini/SEPA repository.

## What it detects

- Breakout today: 20-day, 50-day or 52-week price breakout with volume
- Recent breakout: confirmed during the previous five trading sessions
- Approaching breakout: within the configured distance of a resistance level
- Momentum mover: strong daily price/volume movement or strong five-day return
- Cup with Handle
- Flat Base
- Double Bottom
- Pocket Pivot and Volume Dry-Up
- Ascending Triangle
- IPO Base
- High Tight Flag
- Episodic Pivot

Bull Flag is disabled by default.

## Shared controls retained

- Nifty Total Market universe
- Upstox historical and live quotes
- Telegram delivery
- GitHub Actions
- Relative-strength score and RS-line analysis
- Live-volume confirmation
- Price-band/circuit guard
- Entry, stop, targets and position sizing
- Excel reports

Fundamentals are advisory in this scanner: they are displayed and available
for ranking, but missing data does not suppress a price-and-volume breakout.

## Excel sections

- Decision Board
- Breakouts
- Recent Breakouts
- Approaching
- Momentum Movers
- Daily Watchlist
- individual chart-pattern sheets
- All Stocks and Errors

## Create the separate GitHub repository

1. In GitHub, create a new empty repository named:

   `momentum-breakout-scanner`

2. Extract the release ZIP.
3. Upload **all files and folders inside the extracted folder** to the root of
   the new repository. Do not upload the outer folder itself.
4. Confirm these paths exist in GitHub:

   - `main.py`
   - `breakout_engine.py`
   - `config.py`
   - `patterns/`
   - `tests/`
   - `.github/workflows/daily_scan.yml`
   - `data/fundamentals.csv`

## GitHub Actions secrets

Create these under:

`Settings → Secrets and variables → Actions → Secrets`

- `UPSTOX_ACCESS_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Optional:

- `FUNDAMENTALS_CSV_URL` only when fundamentals are hosted at a private or
  signed downloadable URL.

The same Telegram bot can be reused because this scanner has a distinct alert
heading. A separate bot is optional.

## Fundamentals

Edit `data/fundamentals.csv` using this schema:

```csv
Symbol,As Of Date,EPS Growth YoY %,Previous EPS Growth YoY %,Sales Growth YoY %,Operating Margin %,Previous Operating Margin %
COFORGE,2026-07-01,28,20,18,22.5,21.1
```

If this file is maintained in the repository, leave
`FUNDAMENTALS_CSV_URL` unset.

## Local verification

```powershell
python -m pip install -r requirements.txt
python -m compileall -q .
python -m unittest discover -s tests -t . -v
python main.py
```

## First GitHub run

Open `Actions → Momentum Breakout Scan → Run workflow`.
Download the `momentum-breakout-scan-*` artifact after completion.

The Minervini repository is not modified by this project.
