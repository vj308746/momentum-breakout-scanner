from __future__ import annotations

import time

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
