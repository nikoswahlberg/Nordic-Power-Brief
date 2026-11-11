"""Perfect-hindsight battery arbitrage on day-ahead prices.

Exact optimum via dynamic programming over state of charge (SoC).
Each interval the battery either charges at full power, idles, or
discharges at full power. No forecasting: day-ahead prices for a
delivery day are known the afternoon before, so the schedule is the
real best-possible day-ahead strategy for that day.

Cash flows per interval (e = power * interval length, in MWh):
    charge:    -price * e / eta        (buy more than you store)
    discharge: +price * e * eta - wear * e
where eta is the one-way efficiency (sqrt of round-trip).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Battery

CHARGE, IDLE, DISCHARGE = 1, 0, -1


@dataclass
class DayResult:
    schedule: pd.DataFrame  # per interval: price, action, grid_mw, soc_mwh, cash_eur
    summary: dict


def optimise(prices: pd.Series, bat: Battery, start_soc_mwh: float = 0.0) -> DayResult:
    if prices.empty:
        raise ValueError("Empty price series")
    dt_h = _interval_hours(prices)
    e = bat.power_mw * dt_h                         # MWh moved in one interval
    levels = round(bat.capacity_mwh / e)       # SoC grid: 0..levels
    if not np.isclose(levels * e, bat.capacity_mwh):
        raise ValueError("capacity_mwh must be a multiple of power_mw * interval length")
    s0 = round(start_soc_mwh / e)

    p = prices.to_numpy(dtype=float)
    T = len(p)
    eta = bat.one_way_eff
    buy = -p * e / eta
    sell = p * e * eta - bat.degradation_eur_per_mwh * e

    # Cycle cap: count discharge steps used so far (k). One full cycle = `levels` steps.
    k_max = T if bat.max_cycles_per_day is None else round(bat.max_cycles_per_day * levels)
    k_max = min(k_max, T)

    # value[t, s, k] = best cash from interval t onward with SoC level s and k discharge steps used
    value = np.zeros((T + 1, levels + 1, k_max + 1))
    choice = np.zeros((T, levels + 1, k_max + 1), dtype=int)
    for t in range(T - 1, -1, -1):
        for s in range(levels + 1):
            for k in range(k_max + 1):
                best, act = value[t + 1, s, k], IDLE
                if s < levels and buy[t] + value[t + 1, s + 1, k] > best + 1e-9:
                    best, act = buy[t] + value[t + 1, s + 1, k], CHARGE
                if s > 0 and k < k_max and sell[t] + value[t + 1, s - 1, k + 1] > best + 1e-9:
                    best, act = sell[t] + value[t + 1, s - 1, k + 1], DISCHARGE
                value[t, s, k], choice[t, s, k] = best, act

    actions, socs, cash = [], [], []
    s, k = s0, 0
    for t in range(T):
        a = choice[t, s, k]
        cash.append(buy[t] if a == CHARGE else sell[t] if a == DISCHARGE else 0.0)
        s += 1 if a == CHARGE else -1 if a == DISCHARGE else 0
        k += 1 if a == DISCHARGE else 0
        actions.append(a)
        socs.append(s * e)

    sched = pd.DataFrame(
        {
            "price_eur_mwh": p,
            "action": actions,
            "grid_mw": [-bat.power_mw if a == CHARGE else bat.power_mw if a == DISCHARGE else 0.0 for a in actions],
            "soc_mwh": socs,
            "cash_eur": cash,
        },
        index=prices.index,
    )
    return DayResult(sched, _summarise(sched, bat, e))


def _summarise(sched: pd.DataFrame, bat: Battery, e: float) -> dict:
    ch = sched["action"] == CHARGE
    dis = sched["action"] == DISCHARGE
    discharged = dis.sum() * e
    return {
        "pnl_eur": round(sched["cash_eur"].sum(), 2),
        "charged_mwh": round(ch.sum() * e, 3),
        "discharged_mwh": round(discharged, 3),
        "cycles": round(discharged / bat.capacity_mwh, 2),
        "avg_buy_price": round(sched.loc[ch, "price_eur_mwh"].mean(), 2) if ch.any() else None,
        "avg_sell_price": round(sched.loc[dis, "price_eur_mwh"].mean(), 2) if dis.any() else None,
        "price_avg": round(sched["price_eur_mwh"].mean(), 2),
        "price_min": round(sched["price_eur_mwh"].min(), 2),
        "price_max": round(sched["price_eur_mwh"].max(), 2),
        "negative_intervals": int((sched["price_eur_mwh"] < 0).sum()),
    }


def _interval_hours(prices: pd.Series) -> float:
    if len(prices) < 2:
        return 1.0
    step = pd.Series(prices.index).diff().dropna().mode().iloc[0]
    return step / pd.Timedelta(hours=1)
