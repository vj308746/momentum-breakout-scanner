from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from market_state import LiveMarketState


@dataclass(frozen=True)
class HealthSnapshot:
    connected: bool
    subscribed: int
    last_message_age_seconds: float | None
    stale: bool
    last_error: str


def snapshot(state: LiveMarketState, stale_after_seconds: int = 15) -> HealthSnapshot:
    status: dict[str, Any] = state.status()
    last = float(status.get("last_message_at") or 0)
    age = time.time() - last if last else None
    stale = bool(age is not None and age > stale_after_seconds)
    if not status.get("connected"):
        stale = True
    return HealthSnapshot(
        connected=bool(status.get("connected")),
        subscribed=int(status.get("subscribed") or 0),
        last_message_age_seconds=age,
        stale=stale,
        last_error=str(status.get("last_error") or ""),
    )
