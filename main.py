from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from base_stage import add_base_stage_tracking
from breakout_engine import (
    calculate_breakout_metrics,
    finalise_breakout_report,
    select_breakout_trade_setup,
)
from config import (
    BENCHMARK_SYMBOL,
    DATA_SOURCE,
    DISTRIBUTION_VOLUME_SYMBOL,
    LOG_FILE,
    LTP_OVERLAY_ENABLED,
    LTP_OVERLAY_REQUIRED,
    MARKET_REQUIRE_BULLISH,
    MAX_STOCKS,
    OUTPUT_FILE,
    REQUEST_DELAY_SECONDS,
    STOCK_UNIVERSE_NAME,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_ENABLED,
    UPSTOX_ACCESS_TOKEN,
    WATCHLIST_TEXT_FILE,
)
from decision_engine import add_trade_decisions
from liquidity import add_liquidity_gate
from downloader import (
    download_stock_data,
    load_stock_universe,
)
from instrument_mapper import UpstoxInstrumentMapper
from fundamentals import (
    add_fundamentals_gate,
    load_fundamentals,
)
from ltp_overlay import (
    apply_market_ltp_overlay,
    apply_stock_ltp_overlay,
    fetch_ltp_quotes,
    quote_for_instrument,
)
from market_filter import calculate_market_status
from pattern_engine import (
    analyse_patterns,
    select_pattern_trade_setup,
)
from relative_strength import (
    add_relative_strength_scores,
    calculate_momentum_metrics,
)
from rs_line import calculate_rs_line_metrics
from report import create_excel_report
from sector_strength import add_sector_strength
from notification_manager import send_notifications
from trade_planner import calculate_trade_plan
from trade_score import add_trade_quality_scores
from trend_template import analyse_stock
from vcp_analysis import (
    add_vcp_combined_flags,
    calculate_vcp_metrics,
)
from volume_analysis import (
    add_combined_volume_flags,
    calculate_volume_metrics,
)
from watchlist import (
    create_watchlist_message,
    save_watchlist_message,
    select_watchlist_candidates,
)


class IndiaTimeFormatter(logging.Formatter):
    def formatTime(
        self,
        record: logging.LogRecord,
        datefmt: str | None = None,
    ) -> str:
        value = datetime.fromtimestamp(
            record.created,
            tz=ZoneInfo("Asia/Kolkata"),
        )
        return value.strftime(
            datefmt or "%Y-%m-%d %H:%M:%S"
        )


def configure_logging() -> None:
    formatter = IndiaTimeFormatter(
        "%(asctime)s IST | %(levelname)s | %(message)s"
    )

    file_handler = logging.FileHandler(
        LOG_FILE,
        mode="w",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            file_handler,
            console_handler,
        ],
        force=True,
    )


def choose_data_symbol(
    row: pd.Series,
) -> str:
    if DATA_SOURCE == "upstox":
        value = str(
            row.get(
                "Upstox Instrument Key",
                "",
            )
        ).strip()
    else:
        value = str(
            row.get(
                "Yahoo Symbol",
                "",
            )
        ).strip()

    if not value:
        raise RuntimeError(
            "Data identifier missing for "
            f"{row.get('Symbol', 'unknown')}."
        )

    return value


def load_ltp_overlay(
    constituents: pd.DataFrame,
) -> tuple[
    dict[str, dict[str, Any]],
    str | None,
]:
    """
    Load one bulk LTP snapshot for all equities plus Nifty 50.
    """

    if (
        DATA_SOURCE != "upstox"
        or not LTP_OVERLAY_ENABLED
    ):
        return {}, None

    mapper = UpstoxInstrumentMapper()
    benchmark_key = mapper.resolve(
        BENCHMARK_SYMBOL
    )

    stock_keys = (
        constituents[
            "Upstox Instrument Key"
        ]
        .dropna()
        .astype(str)
        .str.strip()
        .tolist()
    )

    requested_keys = stock_keys + [
        benchmark_key
    ]

    try:
        quotes = fetch_ltp_quotes(
            requested_keys
        )
        logging.info(
            "Upstox LTP overlay loaded: "
            "%s quotes for %s requested instruments",
            len(
                {
                    str(
                        quote.get(
                            "instrument_token",
                            response_key,
                        )
                    )
                    for response_key, quote
                    in quotes.items()
                }
            ),
            len(
                set(requested_keys)
            ),
        )
        return quotes, benchmark_key

    except Exception:
        logging.exception(
            "Unable to load Upstox LTP overlay"
        )

        if LTP_OVERLAY_REQUIRED:
            raise

        return {}, benchmark_key


def main() -> None:
    configure_logging()
    scan_started = time.perf_counter()

    logging.info(
        "Starting Minervini Scanner "
        "v5.0.1 Market Proxy Edition"
    )
    logging.info(
        "Data source: %s",
        DATA_SOURCE,
    )
    logging.info(
        "Upstox access token available: %s",
        bool(
            UPSTOX_ACCESS_TOKEN.strip()
        ),
    )
    logging.info(
        "LTP overlay enabled: %s",
        LTP_OVERLAY_ENABLED,
    )
    logging.info(
        "Telegram enabled: %s",
        TELEGRAM_ENABLED,
    )
    logging.info(
        "Telegram token available: %s",
        bool(
            TELEGRAM_BOT_TOKEN.strip()
        ),
    )
    logging.info(
        "Telegram chat ID available: %s",
        bool(
            TELEGRAM_CHAT_ID.strip()
        ),
    )

    try:
        constituents = (
            load_stock_universe()
        )
    except Exception:
        logging.exception(
            "Unable to download or map "
            "%s constituents",
            STOCK_UNIVERSE_NAME,
        )
        return

    logging.info(
        "Loaded %s constituents from %s (%s mode)",
        len(constituents),
        STOCK_UNIVERSE_NAME,
        (
            "full"
            if MAX_STOCKS is None
            else "test"
        ),
    )

    try:
        fundamentals = load_fundamentals()
        logging.info(
            "Fundamentals rows loaded: %s",
            len(fundamentals),
        )
    except Exception:
        logging.exception(
            "Fundamentals source could not be loaded"
        )
        fundamentals = pd.DataFrame()

    try:
        ltp_quotes, benchmark_key = (
            load_ltp_overlay(
                constituents
            )
        )
    except Exception:
        return

    try:
        benchmark_data = (
            download_stock_data(
                BENCHMARK_SYMBOL
            )
        )

        benchmark_returns = (
            calculate_momentum_metrics(
                benchmark_data
            )
        )

        try:
            distribution_volume_data = (
                download_stock_data(
                    DISTRIBUTION_VOLUME_SYMBOL
                )
            )
            logging.info(
                "Distribution volume proxy loaded: %s",
                DISTRIBUTION_VOLUME_SYMBOL,
            )
        except Exception:
            logging.exception(
                "Unable to load distribution volume proxy; "
                "benchmark-volume fallback will be used"
            )
            distribution_volume_data = None

        market_status = (
            calculate_market_status(
                benchmark_data,
                distribution_volume_data,
            )
        )

        if benchmark_key:
            market_status = (
                apply_market_ltp_overlay(
                    market_status,
                    quote_for_instrument(
                        ltp_quotes,
                        benchmark_key,
                    ),
                )
            )

    except Exception:
        logging.exception(
            "Unable to analyse benchmark"
        )
        return

    logging.info(
        "Market status: %s | "
        "Price %.2f (%s) | "
        "3M %.2f%% | 6M %.2f%% | 12M %.2f%%",
        market_status["Market Status"],
        float(
            market_status["Market Price"]
        ),
        market_status.get(
            "Market Price Source",
            "Historical candle",
        ),
        benchmark_returns["3M Return %"],
        benchmark_returns["6M Return %"],
        benchmark_returns["12M Return %"],
    )

    results: list[
        dict[str, Any]
    ] = []
    errors: list[
        dict[str, str]
    ] = []

    total = len(
        constituents
    )

    for index, row in (
        constituents.iterrows()
    ):
        symbol = str(
            row["Symbol"]
        ).strip()
        data_symbol = ""

        try:
            data_symbol = (
                choose_data_symbol(
                    row
                )
            )

            data = (
                download_stock_data(
                    data_symbol,
                    yahoo_fallback_symbol=str(
                        row.get(
                            "Yahoo Symbol",
                            symbol + ".NS",
                        )
                    ).strip(),
                )
            )

            result = analyse_stock(
                symbol=symbol,
                company_name=str(
                    row["Company Name"]
                ),
                industry=str(
                    row["Industry"]
                ),
                data=data,
            )

            result.update(
                calculate_momentum_metrics(
                    data
                )
            )
            result.update(
                calculate_rs_line_metrics(
                    data,
                    benchmark_data,
                )
            )
            result.update(
                calculate_volume_metrics(
                    data
                )
            )

            vcp_metrics = (
                calculate_vcp_metrics(
                    data
                )
            )
            result.update(
                vcp_metrics
            )

            result.update(
                analyse_patterns(data)
            )
            result.update(
                calculate_breakout_metrics(
                    data
                )
            )
            result.update(
                select_pattern_trade_setup(result)
            )
            result.update(
                select_breakout_trade_setup(
                    result
                )
            )

            result.update(
                calculate_trade_plan(
                    data=data,
                    pivot_price=float(
                        result[
                            "Pattern Pivot Price"
                        ]
                    ),
                )
            )

            if (
                DATA_SOURCE == "upstox"
                and LTP_OVERLAY_ENABLED
            ):
                result = (
                    apply_stock_ltp_overlay(
                        result,
                        quote_for_instrument(
                            ltp_quotes,
                            data_symbol,
                        ),
                    )
                )

            results.append(
                result
            )

            logging.info(
                "[%s/%s] %s | "
                "Price %.2f (%s) | "
                "Trend %s/8 | "
                "Volume %.0f | VCP %.0f",
                index + 1,
                total,
                symbol,
                float(
                    result[
                        "Current Price"
                    ]
                ),
                result.get(
                    "Current Price Source",
                    "Historical candle",
                ),
                result[
                    "Conditions Passed"
                ],
                result[
                    "Volume Score"
                ],
                result[
                    "VCP Score"
                ],
            )

        except Exception as exc:
            errors.append(
                {
                    "Symbol": symbol,
                    "Data Source": (
                        DATA_SOURCE
                    ),
                    "Data Symbol": (
                        data_symbol
                    ),
                    "Company Name": str(
                        row.get(
                            "Company Name",
                            "",
                        )
                    ),
                    "Error": str(exc),
                }
            )

            logging.warning(
                "[%s/%s] %s failed: %s",
                index + 1,
                total,
                symbol,
                exc,
            )

        time.sleep(
            REQUEST_DELAY_SECONDS
        )

    if not results:
        logging.error(
            "No stocks were analysed successfully"
        )
        return

    try:
        report = pd.DataFrame(
            results
        )

        report = (
            add_relative_strength_scores(
                report,
                benchmark_returns,
            )
        )

        report, sector_summary = (
            add_sector_strength(
                report
            )
        )

        report = (
            add_combined_volume_flags(
                report
            )
        )

        report = (
            add_vcp_combined_flags(
                report
            )
        )

        report = add_liquidity_gate(
            report
        )
        logging.info(
            "Liquidity gate completed | Eligible: %s | "
            "Excluded: %s",
            int(report["Liquidity Eligible"].sum()),
            int((~report["Liquidity Eligible"]).sum()),
        )

        report = add_fundamentals_gate(
            report,
            fundamentals,
        )

        report[
            "Market Filter Pass"
        ] = bool(
            market_status[
                "Market Bullish"
            ]
        )

        report[
            "Sector + Final Pass"
        ] = (
            report[
                "Trend + RS + Volume + VCP Pass"
            ].astype(bool)
            & report[
                "Sector RS Pass"
            ].astype(bool)
        )

        report[
            "Trade Environment Pass"
        ] = (
            (
                report[
                    "Sector + Final Pass"
                ]
                & report[
                    "Market Filter Pass"
                ]
            )
            if MARKET_REQUIRE_BULLISH
            else report[
                "Sector + Final Pass"
            ]
        )

        report = (
            add_trade_quality_scores(
                report,
                market_status,
            )
        )
        report = finalise_breakout_report(
            report
        )
        report = add_base_stage_tracking(
            report
        )

        # Decision Engine must run after the LTP overlay and after
        # quality/sector/volume/VCP fields have been calculated.
        logging.info(
            "Decision Engine stage started"
        )

        report = add_trade_decisions(
            report,
            market_status,
        )

        logging.info(
            "Decision Engine completed | "
            "BUY NOW: %s | NEAR TRIGGER: %s | "
            "WATCH: %s | WAIT: %s",
            int(report["Action"].eq("BUY NOW").sum()),
            int(report["Action"].eq("NEAR TRIGGER").sum()),
            int(report["Action"].eq("WATCH").sum()),
            int(report["Action"].eq("WAIT").sum()),
        )

        # Rank after Action Priority and Confidence Score exist.
        report = report.sort_values(
            by=[
                "Action Priority",
                "Confidence Score",
                "Trade Quality Score",
                "RS Score",
                "Sector RS Score",
                "Volume Score",
                "VCP Score",
            ],
            ascending=[
                False,
                False,
                False,
                False,
                False,
                False,
                False,
            ],
        ).reset_index(
            drop=True
        )

        report.insert(
            0,
            "Rank",
            range(
                1,
                len(report) + 1,
            ),
        )

        logging.info(
            "Watchlist filtering and ranking started"
        )

        watchlist = select_watchlist_candidates(
            report
        )

        logging.info(
            "Watchlist completed | Candidates: %s",
            len(watchlist),
        )

        watchlist_message = create_watchlist_message(
            watchlist,
            market_status,
        )

        save_watchlist_message(
            watchlist_message,
            WATCHLIST_TEXT_FILE,
        )

        logging.info(
            "Excel report generation started"
        )

        create_excel_report(
            report=report,
            sector_summary=(
                sector_summary
            ),
            market_status=(
                market_status
            ),
            errors=errors,
            output_file=(
                OUTPUT_FILE
            ),
            watchlist=(
                watchlist
            ),
        )

    except Exception:
        logging.exception(
            "Unable to build final "
            "rankings or reports"
        )
        return

    try:
        send_notifications(
            watchlist_message
        )
    except Exception:
        logging.exception(
            "Notification stage failed"
        )
        return

    overlay_count = int(
        report.get(
            "LTP Overlay Applied",
            pd.Series(
                False,
                index=report.index,
            ),
        ).fillna(False).astype(bool).sum()
    )

    logging.info(
        "Scan complete | Total duration: %.2fs",
        time.perf_counter() - scan_started,
    )
    logging.info(
        "Successful: %s | Errors: %s | "
        "LTP overlaid: %s | BUY NOW: %s | "
        "NEAR TRIGGER: %s | WATCH: %s | WAIT: %s",
        len(results),
        len(errors),
        overlay_count,
        int(
            report[
                "Action"
            ].eq("BUY NOW").sum()
        ),
        int(
            report[
                "Action"
            ].eq("NEAR TRIGGER").sum()
        ),
        int(
            report[
                "Action"
            ].eq("WATCH").sum()
        ),
        int(
            report[
                "Action"
            ].eq("WAIT").sum()
        ),
    )
    logging.info(
        "Excel: %s",
        OUTPUT_FILE,
    )
    logging.info(
        "Watchlist: %s",
        WATCHLIST_TEXT_FILE,
    )

    display_columns = [
        "Rank",
        "Symbol",
        "Action",
        "Confidence Score",
        "Risk Level",
        "Current Price",
        "Suggested Entry",
        "Live Extension %",
        "Suggested Stop Loss",
        "Suggested Quantity",
        "Target 1:2",
        "Target 1:3",
        "EMA 10",
        "EMA 20",
        "EMA 50",
        "Trade Quality Score",
        "Trade Grade",
    ]

    available_columns = [
        column
        for column in display_columns
        if column in report.columns
    ]

    print(
        "\nTop-ranked live decisions:"
    )
    print(
        report[
            available_columns
        ]
        .head(15)
        .to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()
