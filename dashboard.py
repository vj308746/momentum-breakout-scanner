from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from config import (
    DASHBOARD_DEFAULT_ROWS,
    DASHBOARD_TITLE,
    OUTPUT_FILE,
)


st.set_page_config(
    page_title=DASHBOARD_TITLE,
    layout="wide",
)

st.title(
    DASHBOARD_TITLE
)
st.caption(
    "Live decision output based on Upstox LTP, "
    "historical pattern quality and configured risk rules."
)


@st.cache_data(
    show_spinner=False,
)
def load_workbook(
    path: str,
    modified_time: float,
) -> dict[str, pd.DataFrame]:
    del modified_time
    return pd.read_excel(
        path,
        sheet_name=None,
    )


report_path = Path(
    OUTPUT_FILE
)

if not report_path.exists():
    st.error(
        f"Report not found: {report_path}. "
        "Run python main.py first."
    )
    st.stop()

workbook = load_workbook(
    str(report_path),
    report_path.stat().st_mtime,
)

all_stocks = workbook.get(
    "All Stocks",
    pd.DataFrame(),
)
market_status = workbook.get(
    "Market Status",
    pd.DataFrame(),
)
sector_leaders = workbook.get(
    "Sector Leaders",
    pd.DataFrame(),
)

if all_stocks.empty:
    st.warning(
        "The All Stocks sheet is empty."
    )
    st.stop()

if not market_status.empty:
    market_row = (
        market_status.iloc[0]
    )

    first, second, third, fourth = (
        st.columns(4)
    )

    first.metric(
        "Market",
        str(
            market_row.get(
                "Market Status",
                "Unknown",
            )
        ),
    )

    second.metric(
        "Market Price",
        (
            f"{float(market_row.get('Market Price', 0)):,.2f}"
        ),
    )

    second.caption(
        str(
            market_row.get(
                "Market Price Source",
                "",
            )
        )
    )

    third.metric(
        "50 DMA",
        (
            f"{float(market_row.get('Market 50 DMA', 0)):,.2f}"
        ),
    )

    fourth.metric(
        "200 DMA",
        (
            f"{float(market_row.get('Market 200 DMA', 0)):,.2f}"
        ),
    )

st.subheader(
    "Decision Summary"
)

summary_columns = st.columns(5)

summary_items = [
    (
        "BUY NOW",
        "BUY NOW",
    ),
    (
        "WATCH",
        "WATCH",
    ),
    (
        "BREAKOUT WAIT",
        "BUY ON BREAKOUT",
    ),
    (
        "HOLD / NO ADD",
        "BREAKOUT / VOLUME PENDING",
    ),
    (
        "EXTENDED",
        "EXTENDED / DO NOT CHASE",
    ),
]

for column, (
    label,
    action,
) in zip(
    summary_columns,
    summary_items,
):
    column.metric(
        label,
        int(
            all_stocks[
                "Action"
            ].eq(action).sum()
        ),
    )

st.subheader(
    "Filters"
)

filter_one, filter_two, filter_three, filter_four = (
    st.columns(4)
)

actions = (
    all_stocks["Action"]
    .dropna()
    .astype(str)
    .unique()
    .tolist()
)

selected_actions = (
    filter_one.multiselect(
        "Actions",
        options=actions,
        default=[
            action
            for action in actions
            if action
            in {
                "BUY NOW",
                "WATCH",
                "BUY ON BREAKOUT",
            }
        ],
    )
)

minimum_confidence = (
    filter_two.slider(
        "Minimum confidence",
        min_value=0,
        max_value=100,
        value=70,
    )
)

risk_levels = (
    all_stocks[
        "Risk Level"
    ]
    .dropna()
    .astype(str)
    .unique()
    .tolist()
)

selected_risks = (
    filter_three.multiselect(
        "Risk levels",
        options=risk_levels,
        default=risk_levels,
    )
)

search_symbol = (
    filter_four.text_input(
        "Search symbol",
        value="",
    )
    .strip()
    .upper()
)

filtered = all_stocks.copy()

if selected_actions:
    filtered = filtered[
        filtered["Action"]
        .astype(str)
        .isin(
            selected_actions
        )
    ]

filtered = filtered[
    pd.to_numeric(
        filtered[
            "Confidence Score"
        ],
        errors="coerce",
    )
    .fillna(0)
    >= minimum_confidence
]

if selected_risks:
    filtered = filtered[
        filtered[
            "Risk Level"
        ]
        .astype(str)
        .isin(
            selected_risks
        )
    ]

if search_symbol:
    filtered = filtered[
        filtered["Symbol"]
        .astype(str)
        .str.upper()
        .str.contains(
            search_symbol,
            regex=False,
        )
    ]

filtered = filtered.sort_values(
    by=[
        "Action Priority",
        "Confidence Score",
        "Trade Quality Score",
    ],
    ascending=[
        True,
        False,
        False,
    ],
)

display_columns = [
    column
    for column in [
        "Rank",
        "Symbol",
        "Company Name",
        "Industry",
        "Action",
        "Confidence Score",
        "Trade Urgency",
        "Risk Level",
        "Current Price",
        "Suggested Entry",
        "Live Extension %",
        "Suggested Stop Loss",
        "Suggested Quantity",
        "Planned Investment",
        "Actual Rupee Risk",
        "Target 1:2",
        "Target 1:3",
        "EMA 10",
        "EMA 20",
        "EMA 50",
        "EMA Bullish Alignment",
        "Trade Quality Score",
        "Trade Grade",
        "RS Score",
        "Sector RS Score",
        "Volume Score",
        "VCP Score",
        "Decision Reason",
    ]
    if column in filtered.columns
]

st.subheader(
    "Live Trade Decisions"
)

st.dataframe(
    filtered[
        display_columns
    ].head(
        DASHBOARD_DEFAULT_ROWS
    ),
    use_container_width=True,
    hide_index=True,
)

st.subheader(
    "Stock Decision Card"
)

available_symbols = (
    filtered["Symbol"]
    .astype(str)
    .tolist()
)

if not available_symbols:
    st.info(
        "No stocks match the selected filters."
    )
else:
    selected_symbol = (
        st.selectbox(
            "Select stock",
            available_symbols,
        )
    )

    stock = filtered[
        filtered["Symbol"]
        .astype(str)
        .eq(selected_symbol)
    ].iloc[0]

    action_one, action_two, action_three, action_four = (
        st.columns(4)
    )

    action_one.metric(
        "Action",
        str(
            stock["Action"]
        ),
    )

    action_two.metric(
        "Confidence",
        (
            f"{float(stock['Confidence Score']):.1f}%"
        ),
    )

    action_three.metric(
        "Risk",
        str(
            stock["Risk Level"]
        ),
    )

    action_four.metric(
        "Urgency",
        str(
            stock["Trade Urgency"]
        ),
    )

    one, two, three, four = (
        st.columns(4)
    )

    one.metric(
        "Current",
        (
            f"₹{float(stock['Current Price']):,.2f}"
        ),
    )

    two.metric(
        "Entry",
        (
            f"₹{float(stock['Suggested Entry']):,.2f}"
        ),
        (
            f"{float(stock['Live Extension %']):+.2f}%"
        ),
    )

    three.metric(
        "Stop",
        (
            f"₹{float(stock['Suggested Stop Loss']):,.2f}"
        ),
    )

    four.metric(
        "Quantity",
        (
            f"{int(stock['Suggested Quantity'])}"
        ),
    )

    five, six, seven, eight = (
        st.columns(4)
    )

    five.metric(
        "Target 1:2",
        (
            f"₹{float(stock['Target 1:2']):,.2f}"
        ),
    )

    six.metric(
        "Target 1:3",
        (
            f"₹{float(stock['Target 1:3']):,.2f}"
        ),
    )

    seven.metric(
        "Investment",
        (
            f"₹{float(stock['Planned Investment']):,.2f}"
        ),
    )

    eight.metric(
        "Planned Loss",
        (
            f"₹{float(stock['Actual Rupee Risk']):,.2f}"
        ),
    )

    st.write(
        "**Decision:** "
        + str(
            stock.get(
                "Decision Reason",
                "",
            )
        )
    )

    st.write(
        "**Why selected:** "
        + str(
            stock.get(
                "Why Selected",
                "",
            )
        )
    )

    st.write(
        "**EMA panel:** "
        f"10 EMA ₹{float(stock['EMA 10']):,.2f}, "
        f"20 EMA ₹{float(stock['EMA 20']):,.2f}, "
        f"50 EMA ₹{float(stock['EMA 50']):,.2f}"
    )

    st.write(
        "**Trailing plan:** "
        + str(
            stock.get(
                "Trailing Stop Plan",
                "",
            )
        )
    )

if not sector_leaders.empty:
    st.subheader(
        "Sector Rotation"
    )

    st.dataframe(
        sector_leaders.head(15),
        use_container_width=True,
        hide_index=True,
    )
