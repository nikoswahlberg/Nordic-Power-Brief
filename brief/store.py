"""Plain CSV storage: small, diffable in git, readable on GitHub."""

from __future__ import annotations

from datetime import date

import pandas as pd

from . import config


def _pnl_log():
    return config.DATA_DIR / "battery_pnl.csv"


def save_schedule(sched: pd.DataFrame, day: date, zone: str) -> None:
    path = config.DATA_DIR / "schedules" / f"{zone}_{day.isoformat()}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    sched.to_csv(path, index_label="start_utc")


def load_schedule(day: date, zone: str) -> pd.DataFrame:
    path = config.DATA_DIR / "schedules" / f"{zone}_{day.isoformat()}.csv"
    return pd.read_csv(path, index_col="start_utc", parse_dates=["start_utc"])


def upsert_pnl(day: date, zone: str, summary: dict) -> pd.DataFrame:
    row = pd.DataFrame([{"date": day.isoformat(), "zone": zone, **summary}])
    if _pnl_log().exists():
        log = pd.read_csv(_pnl_log())
        log = log[~((log["date"] == day.isoformat()) & (log["zone"] == zone))]
        log = pd.concat([log, row], ignore_index=True)
    else:
        _pnl_log().parent.mkdir(parents=True, exist_ok=True)
        log = row
    log = log.sort_values(["zone", "date"]).reset_index(drop=True)
    log.to_csv(_pnl_log(), index=False)
    return log


def load_pnl() -> pd.DataFrame:
    return pd.read_csv(_pnl_log()) if _pnl_log().exists() else pd.DataFrame()
