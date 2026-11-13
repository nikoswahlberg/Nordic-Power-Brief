"""Daily entry point.

    python -m brief.run                       # today's delivery day (Helsinki), plus any missing days of the last 30
    python -m brief.run --date 2026-11-10     # one specific day
    python -m brief.run --backfill 2026-10-01 2026-11-10
    python -m brief.run --demo                # synthetic prices, no API token, writes to demo/
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from . import battery, config, entsoe, report, store, validate
from .config import DEFAULT_BATTERY, DEFAULT_ZONE, LOCAL_TZ


def process_day(day: date, zone: str, prices: pd.Series | None = None) -> dict:
    if prices is None:
        prices = entsoe.get_day_ahead(day, zone)
    validate.check_day_prices(prices, day)
    result = battery.optimise(prices, DEFAULT_BATTERY)
    store.save_schedule(result.schedule, day, zone)
    store.upsert_pnl(day, zone, result.summary)
    print(f"{day} {zone}: P&L {result.summary['pnl_eur']:.0f} EUR, {result.summary['cycles']} cycles")
    return result.summary


def build_report(day: date, zone: str) -> None:
    sched = store.load_schedule(day, zone)
    log = store.load_pnl()
    summary = log[(log["date"] == day.isoformat()) & (log["zone"] == zone)].iloc[0].to_dict()
    report.render(day, zone, sched, summary, log, DEFAULT_BATTERY)


def _days(a: date, b: date):
    while a <= b:
        yield a
        a += timedelta(days=1)


def missing_days(log: pd.DataFrame, zone: str, start: date, end: date) -> list[date]:
    """Days in [start, end] that have no row in the P&L log."""
    have = set(log.loc[log["zone"] == zone, "date"]) if len(log) else set()
    return [d for d in _days(start, end) if d.isoformat() not in have]


def fill_history(day: date, zone: str) -> None:
    """Fetch any day of the history window before `day` that is not logged yet (first run, missed runs).

    A day that cannot be fetched only raises a warning: the run still fails loudly if `day` itself fails.
    """
    start = day - timedelta(days=config.HISTORY_DAYS - 1)
    for d in missing_days(store.load_pnl(), zone, start, day - timedelta(days=1)):
        try:
            process_day(d, zone)
        except Exception as exc:  # noqa: BLE001 - one bad past day must not block today's brief
            print(f"::warning::Could not fill {d}: {exc}")


def synthetic_prices(day: date, seed: int) -> pd.Series:
    """Rough Nordic winter shape: morning and evening peaks, windy nights, occasional negatives."""
    start, end = entsoe.delivery_window_utc(day)
    idx = pd.date_range(start, end, freq="15min", inclusive="left")
    rng = np.random.default_rng(seed)
    hour = idx.tz_convert(LOCAL_TZ).hour + idx.tz_convert(LOCAL_TZ).minute / 60
    shape = 25 * np.exp(-((hour - 8.5) ** 2) / 4) + 35 * np.exp(-((hour - 18) ** 2) / 5)
    level = rng.uniform(20, 70)
    wind = rng.uniform(0, 1) * 40 * (1 + np.cos(2 * np.pi * hour / 24)) / 2
    p = level + shape - wind + rng.normal(0, 3, len(idx))
    return pd.Series(np.round(p, 2), index=idx, name="price_eur_mwh")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=date.fromisoformat)
    ap.add_argument("--backfill", nargs=2, type=date.fromisoformat, metavar=("START", "END"))
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    zone = DEFAULT_ZONE

    today = datetime.now(LOCAL_TZ).date()

    if args.demo:
        config.DATA_DIR = config.ROOT / "demo" / "data"
        config.DOCS_DIR = config.ROOT / "demo" / "docs"
        for i, d in enumerate(_days(today - timedelta(days=config.HISTORY_DAYS - 1), today)):
            process_day(d, zone, synthetic_prices(d, seed=i))
        build_report(today, zone)
        print(f"Demo report: {config.DOCS_DIR / 'index.html'}")
        return

    if args.backfill:
        failed = []
        for d in _days(*args.backfill):
            try:
                process_day(d, zone)
            except Exception as exc:  # keep going, report at the end
                failed.append(f"{d}: {exc}")
        if failed:
            print("Failed days:\n  " + "\n  ".join(failed))
        report_day = args.backfill[1]
    else:
        report_day = args.date or today
        fill_history(report_day, zone)
        process_day(report_day, zone)

    build_report(report_day, zone)


if __name__ == "__main__":
    main()
