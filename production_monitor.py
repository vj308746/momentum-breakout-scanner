from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from market_state import LiveMarketState


@dataclass(frozen=True)
class HealthSnapshot:
    connected: bool
    requested: int
    subscribed: int
    live: int
    last_message_age_seconds: float | None
    stale: bool
    last_error: str
    subscription_errors: int


def snapshot(state: LiveMarketState, stale_after_seconds: int = 15) -> HealthSnapshot:
    status: dict[str, Any] = state.status()
    # Market-info/heartbeat messages are not proof that instrument data is live.
    last = float(status.get("last_live_message_at") or 0)
    age = time.time() - last if last else None
    stale = bool(age is not None and age > stale_after_seconds)
    if not status.get("connected"):
        stale = True
    return HealthSnapshot(
        connected=bool(status.get("connected")),
        requested=int(status.get("requested") or 0),
        subscribed=int(status.get("subscribed") or 0),
        live=int(status.get("live") or 0),
        last_message_age_seconds=age,
        stale=stale,
        last_error=str(status.get("last_error") or ""),
        subscription_errors=int(status.get("subscription_errors") or 0),
    )
