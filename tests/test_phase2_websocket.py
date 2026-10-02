import pandas as pd

from live_data import LiveUpstoxData
from upstox_market_stream import UpstoxMarketStream, _feed_response_class


class FakeClient:
    access_token = "token"


class FakeMapper:
    def resolve(self, symbol):
        return f"NSE_EQ|{symbol}"


def test_websocket_feed_decodes_live_i1():
    cls = _feed_response_class()
    response = cls()
    feed = response.feeds["NSE_EQ|TEST"]
    feed.fullFeed.marketFF.ltpc.ltp = 123.4
    feed.fullFeed.marketFF.marketOHLC.ohlc.add(
        interval="I1", open=120, high=124, low=119, close=123.4, vol=100, ts=1000
    )
    stream = UpstoxMarketStream("token")
    stream._handle(response.SerializeToString())
    data = stream.snapshot()["NSE_EQ|TEST"]
    assert data["ltp"] == 123.4
    assert data["i1"]["close"] == 123.4


def test_minute_aggregation_produces_requested_timeframe():
    idx = pd.date_range("2026-10-01 09:15", periods=10, freq="min", tz="UTC")
    frame = pd.DataFrame(
        {
            "Open": range(100, 110),
            "High": range(101, 111),
            "Low": range(99, 109),
            "Close": range(100, 110),
            "Volume": [10] * 10,
        },
        index=idx,
    )
    result = LiveUpstoxData(FakeClient(), FakeMapper())._aggregate_minute(frame, "5m")
    assert len(result) == 2
    assert result.iloc[0]["Open"] == 100
    assert result.iloc[0]["High"] == 105
    assert result.iloc[0]["Volume"] == 50
