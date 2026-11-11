"""Data checks. A failed check raises, which turns the GitHub Actions run red: that is the alert."""

from __future__ import annotations

from datetime import date

import pandas as pd

from .entsoe import delivery_window_utc

PRICE_FLOOR, PRICE_CAP = -500.0, 4000.0  # SDAC harmonised min/max clearing prices


def check_day_prices(prices: pd.Series, day: date) -> None:
    start, end = delivery_window_utc(day)
    if prices.empty:
        raise ValueError(f"{day}: no prices")
    step = pd.Series(prices.index).diff().dropna().mode().iloc[0]
    expected = int((end - start) / step)  # 92 / 96 / 100 at 15 min on DST days
    problems = []
    if len(prices) != expected:
        problems.append(f"expected {expected} intervals, got {len(prices)}")
    if prices.index.has_duplicates:
        problems.append("duplicate timestamps")
    if prices.isna().any():
        problems.append(f"{int(prices.isna().sum())} missing prices")
    out_of_range = prices[(prices < PRICE_FLOOR) | (prices > PRICE_CAP)]
    if not out_of_range.empty:
        problems.append(f"{len(out_of_range)} prices outside [{PRICE_FLOOR}, {PRICE_CAP}]")
    if problems:
        raise ValueError(f"{day}: " + "; ".join(problems))
