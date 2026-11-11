import numpy as np
import pandas as pd
import pytest

from brief.battery import CHARGE, DISCHARGE, optimise
from brief.config import Battery

IDEAL = Battery(power_mw=1, capacity_mwh=2, round_trip_eff=1.0, degradation_eur_per_mwh=0, max_cycles_per_day=None)


def hourly(values):
    idx = pd.date_range("2026-11-10 22:00", periods=len(values), freq="h", tz="UTC")
    return pd.Series(values, index=idx, dtype=float)


def test_flat_prices_no_trading():
    r = optimise(hourly([50] * 24), IDEAL)
    assert r.summary["pnl_eur"] == 0
    assert (r.schedule["action"] == 0).all()


def test_simple_two_level_day():
    # cheap first 12 h, expensive last 12 h: buy 2 MWh at 10, sell at 100
    r = optimise(hourly([10] * 12 + [100] * 12), IDEAL)
    assert r.summary["pnl_eur"] == pytest.approx(2 * 100 - 2 * 10)
    assert r.summary["cycles"] == 1


def test_cannot_sell_before_buying():
    # expensive first, cheap later: starting empty, nothing to sell
    r = optimise(hourly([100] * 12 + [10] * 12), IDEAL)
    assert r.summary["pnl_eur"] == 0


def test_efficiency_and_wear_reduce_profit():
    prices = hourly([10] * 12 + [100] * 12)
    ideal = optimise(prices, IDEAL).summary["pnl_eur"]
    real = optimise(prices, Battery(round_trip_eff=0.88, degradation_eur_per_mwh=5)).summary["pnl_eur"]
    assert 0 < real < ideal


def test_small_spread_not_worth_cycling():
    # spread of 2 EUR/MWh is below losses + wear, so stay idle
    r = optimise(hourly([50] * 12 + [52] * 12), Battery())
    assert r.summary["cycles"] == 0


def test_negative_prices_are_paid_to_charge():
    r = optimise(hourly([-20] * 12 + [5] * 12), IDEAL)
    assert r.summary["pnl_eur"] == pytest.approx(2 * 20 + 2 * 5)


def test_soc_stays_in_bounds_15min():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2026-11-10 22:00", periods=96, freq="15min", tz="UTC")
    prices = pd.Series(rng.normal(60, 30, 96), index=idx)
    r = optimise(prices, Battery())
    assert r.schedule["soc_mwh"].between(0, 2).all()
    assert set(r.schedule["action"]) <= {CHARGE, DISCHARGE, 0}


def test_matches_brute_force_on_small_case():
    # exhaustive search over all action sequences for a short horizon
    import itertools

    prices = [30, 5, 80, 20, 90, 10]
    bat = Battery(power_mw=1, capacity_mwh=2, round_trip_eff=0.81, degradation_eur_per_mwh=3, max_cycles_per_day=None)
    eta = bat.one_way_eff
    best = 0.0
    for seq in itertools.product([1, 0, -1], repeat=len(prices)):
        soc, cash, ok = 0, 0.0, True
        for p, a in zip(prices, seq, strict=True):
            soc += a
            if not 0 <= soc <= 2:
                ok = False
                break
            cash += -p / eta if a == 1 else (p * eta - 3) if a == -1 else 0
        if ok:
            best = max(best, cash)
    assert optimise(hourly(prices), bat).summary["pnl_eur"] == pytest.approx(best, abs=0.01)


def test_cycle_cap_is_respected_and_binds():
    # two clean arbitrage windows per day: uncapped does 2 cycles, capped at 1 does 1
    prices = hourly(([10] * 6 + [100] * 6) * 2)
    free = optimise(prices, IDEAL)
    capped = optimise(prices, Battery(round_trip_eff=1.0, degradation_eur_per_mwh=0, max_cycles_per_day=1))
    assert free.summary["cycles"] == 2
    assert capped.summary["cycles"] == 1
    assert capped.summary["pnl_eur"] == pytest.approx(free.summary["pnl_eur"] / 2)
