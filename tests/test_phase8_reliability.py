from __future__ import annotations

import time

import pandas as pd

from production_monitor import snapshot
from upstox_market_stream import UpstoxMarketStream


class FakeWS:
    def __init__(self):
        self.messages: list[bytes] = []

    def send(self, payload: bytes) -> None:
        self.messages.append(payload)


def test_desired_instruments_are_tracked_before_socket_connects():
    stream = UpstoxMarketStream("token")
    stream.set_instruments(["A", "B", "A"])

    assert stream.requested_instruments() == {"A", "B"}
    assert stream.subscribed_instruments() == set()
    assert stream.live_instruments() == set()
    assert stream._wake.is_set()


def test_subscription_sync_handles_add_and_remove():
    stream = UpstoxMarketStream("token")
    fake = FakeWS()
    stream._ws = fake

    stream.set_instruments(["A", "B", "C"])
    stream._sync_subscriptions()

    assert stream.subscribed_instruments() == {"A", "B", "C"}
    assert len(fake.messages) == 1
    assert b'"method": "sub"' in fake.messages[0]

    stream.set_instruments(["B"])
    stream._sync_subscriptions()

    assert stream.subscribed_instruments() == {"B"}
    assert len(fake.messages) == 2
    assert b'"method": "unsub"' in fake.messages[1]


def test_health_uses_live_data_timestamp():
    stream = UpstoxMarketStream("token")
    stream.connected = True
    stream.last_message_at = time.time()
    stream.last_live_message_at = 0.0

    class State:
        def status(self):
            return {
                "connected": True,
                "requested": 2,
                "subscribed": 2,
                "live": 0,
                "last_live_message_at": stream.last_live_message_at,
                "last_error": "",
                "subscription_errors": 0,
            }

    health = snapshot(State(), stale_after_seconds=15)

    assert health.stale is True
    assert health.requested == 2
    assert health.live == 0


def test_warmup_is_cached_for_the_current_trading_session(monkeypatch):
    from market_state import LiveMarketState

    class FakeMapper:
        def resolve(self, symbol):
            return "NSE_EQ|FAKE"

    class FakeClient:
        access_token = "token"
        def __init__(self):
            self.calls = 0
        def get_intraday_candles(self, key, unit, interval):
            self.calls += 1
            return [["2026-10-06T09:15:00+05:30", 100, 101, 99, 100.5, 1000, 0]]

    state = LiveMarketState(client=FakeClient(), mapper=FakeMapper())
    state.stream = type("Stream", (), {"snapshot": lambda self: {}})()
    first = state._warmup("FAKE")
    second = state._warmup("FAKE")

    assert not first.empty
    assert not second.empty
    assert state.client.calls == 1
    assert state.warmup_status()["warmed"] == 1


def test_scanner_publishes_results_as_symbols_complete():
    from realtime_scanner import RealTimeBreakoutScanner, ScannerConfig

    class FakeLive:
        def __init__(self):
            self.mapper = type("Mapper", (), {"instruments": pd.DataFrame()})()
            self.started = []
        def start_stream(self, symbols):
            self.started.extend(symbols)
        def live_candles(self, symbol, timeframe):
            return pd.DataFrame({
                "Open": [100.0] * 30,
                "High": [101.0] * 30,
                "Low": [99.0] * 30,
                "Close": [100.0] * 30,
                "Volume": [1000.0] * 30,
            }, index=pd.date_range("2026-10-06", periods=30, freq="min", tz="UTC"))

    live = FakeLive()
    scanner = RealTimeBreakoutScanner(live)
    seen = []
    scanner.scan(pd.DataFrame({"Symbol": ["AAA", "BBB"]}), ScannerConfig(max_symbols=2, warmup_workers=1), on_result=seen.append)
    assert {row["Symbol"] for row in seen} == {"AAA", "BBB"}
