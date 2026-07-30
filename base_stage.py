from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from config import (
    BASE_STAGE_ENABLED,
    BASE_STAGE_MAX_ELIGIBLE,
    BASE_STAGE_MIN_DAYS_BETWEEN,
    BASE_STAGE_NEW_PIVOT_PCT,
    BASE_STAGE_STATE_FILE,
)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def add_base_stage_tracking(
    report: pd.DataFrame,
    state_file: Path = BASE_STAGE_STATE_FILE,
    as_of: date | None = None,
) -> pd.DataFrame:
    frame = report.copy()
    if not BASE_STAGE_ENABLED:
        frame["Base Stage"] = 1
        frame["Base Stage Pass"] = True
        return frame

    today = as_of or date.today()
    state = _load_state(Path(state_file))
    stages: list[int] = []

    for _, row in frame.iterrows():
        symbol = str(row["Symbol"])
        pivot = float(
            row.get("Pattern Pivot Price", 0)
            or row.get("Pivot Price", 0)
            or 0
        )
        pattern = str(
            row.get("Primary Pattern", "Unknown")
        )
        current = float(row.get("Current Price", 0) or 0)
        record = state.get(symbol, {})
        stage = int(record.get("stage", 1))
        old_pivot = float(record.get("pivot", 0) or 0)
        old_pattern = str(record.get("pattern", ""))
        last_base = record.get("last_base_date")
        days_since = 9999
        if last_base:
            try:
                days_since = (
                    today
                    - datetime.fromisoformat(last_base).date()
                ).days
            except ValueError:
                pass
        pivot_change = (
            abs(pivot / old_pivot - 1) * 100
            if pivot > 0 and old_pivot > 0
            else 0.0
        )
        new_base = (
            bool(record.get("breakout_seen", False))
            and days_since >= BASE_STAGE_MIN_DAYS_BETWEEN
            and pivot_change >= BASE_STAGE_NEW_PIVOT_PCT
        )
        if new_base:
            stage += 1
            record["breakout_seen"] = False
            record["last_base_date"] = today.isoformat()
        if not record:
            record["last_base_date"] = today.isoformat()
        if pivot > 0 and current >= pivot:
            record["breakout_seen"] = True
        record.update(
            {
                "stage": stage,
                "pivot": pivot,
                "pattern": pattern,
                "last_seen": today.isoformat(),
            }
        )
        state[symbol] = record
        stages.append(stage)

    _save_state(Path(state_file), state)
    frame["Base Stage"] = stages
    frame["Base Stage Pass"] = (
        frame["Base Stage"]
        <= BASE_STAGE_MAX_ELIGIBLE
    )
    return frame
