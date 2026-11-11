"""Render docs/index.html (served by GitHub Pages)."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
from plotly.subplots import make_subplots

from . import config
from .config import LOCAL_TZ, Battery


def _fmt(x, decimals=0, unit=""):
    """European number format: space thousands separator, comma decimals."""
    if x is None or pd.isna(x):
        return "–"
    s = f"{x:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return f"{s} {unit}".strip()


def _schedule_chart(sched: pd.DataFrame) -> str:
    local = sched.copy()
    local.index = pd.to_datetime(local.index, utc=True).tz_convert(LOCAL_TZ)
    p_max = float(local["grid_mw"].abs().max() or 1)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for label, mask, colour in [("Charging (buy), MW", local["grid_mw"] < 0, "#e76f51"),
                                ("Discharging (sell), MW", local["grid_mw"] > 0, "#2a9d8f")]:
        fig.add_bar(x=local.index, y=local["grid_mw"].where(mask, 0), name=label, marker_color=colour,
                    opacity=0.5, secondary_y=True)
    fig.add_scatter(x=local.index, y=local["price_eur_mwh"], line_shape="hv", name="Day-ahead price, €/MWh",
                    line={"color": "#264653", "width": 2}, secondary_y=False)
    fig.update_layout(height=380, margin={"l": 40, "r": 40, "t": 10, "b": 30},
                      legend={"orientation": "h", "y": -0.15}, separators=", ", template="simple_white",
                      bargap=0, barmode="overlay")
    fig.update_yaxes(title_text="€/MWh", secondary_y=False)
    fig.update_yaxes(title_text="MW", secondary_y=True, range=[-2 * p_max, 2 * p_max], dtick=p_max, showgrid=False)
    return fig.to_html(include_plotlyjs="cdn", full_html=False)


def _history_chart(log: pd.DataFrame) -> str:
    log = log.copy()
    log["cum"] = log["pnl_eur"].cumsum()
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=log["date"], y=log["pnl_eur"], name="Daily P&L, €", marker_color="#8ab17d")
    fig.add_scatter(x=log["date"], y=log["cum"], name="Cumulative, €", line=dict(color="#264653"), secondary_y=True)
    fig.update_layout(height=320, margin=dict(l=40, r=40, t=10, b=30), legend=dict(orientation="h", y=-0.2),
                      separators=", ", template="simple_white")
    fig.update_yaxes(rangemode="tozero")
    return fig.to_html(include_plotlyjs=False, full_html=False)


def _cumulative_chart(last30: pd.DataFrame) -> str:
    """Cumulative P&L over the 30-day window, starting from zero, so the end point equals the 'Last 30 days' KPI."""
    fig = make_subplots()
    fig.add_scatter(x=last30["date"], y=last30["pnl_eur"].cumsum(), mode="lines+markers", fill="tozeroy",
                    name="Cumulative P&L, €", line={"color": "#2a9d8f"},
                    hovertemplate="%{x}<br>%{y:,.0f} €<extra></extra>")
    fig.update_layout(height=300, margin={"l": 40, "r": 40, "t": 10, "b": 30}, showlegend=False,
                      separators=", ", template="simple_white")
    fig.update_yaxes(title_text="€", rangemode="tozero")
    return fig.to_html(include_plotlyjs=False, full_html=False)


def render(day: date, zone: str, sched: pd.DataFrame, summary: dict, log: pd.DataFrame, bat: Battery) -> None:
    log = log[log["zone"] == zone].sort_values("date")
    last30 = log.tail(30)
    annualised_per_mw = last30["pnl_eur"].mean() * 365 / bat.power_mw if len(last30) else None
    spread = (summary["avg_sell_price"] - summary["avg_buy_price"]) if summary["avg_sell_price"] else None

    kpis = [
        ("P&L for the day", _fmt(summary["pnl_eur"], 0, "€")),
        ("Cycles", _fmt(summary["cycles"], 2)),
        ("Captured spread", _fmt(spread, 1, "€/MWh")),
        ("Price min / avg / max", " / ".join(_fmt(summary[k], 1) for k in ("price_min", "price_avg", "price_max"))),
        ("Last 30 days", _fmt(last30["pnl_eur"].sum(), 0, "€")),
        ("30-day pace, €/MW/year", _fmt(annualised_per_mw, 0)),
    ]
    kpi_html = "".join(f'<div class="kpi"><div class="v">{v}</div><div class="l">{k}</div></div>' for k, v in kpis)
    table = (
        log.tail(14).iloc[::-1][["date", "pnl_eur", "cycles", "avg_buy_price", "avg_sell_price", "negative_intervals"]]
        .rename(columns={"date": "Date", "pnl_eur": "P&L €", "cycles": "Cycles", "avg_buy_price": "Avg buy €/MWh",
                         "avg_sell_price": "Avg sell €/MWh", "negative_intervals": "Neg. price intervals"})
        .to_html(index=False, border=0, classes="tbl", na_rep="–",
                 float_format=lambda x: f"{x:,.2f}".replace(",", " ").replace(".", ","))
    )
    cap = _fmt(bat.max_cycles_per_day, 1) if bat.max_cycles_per_day else "∞"
    generated = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nordic Power Brief – {zone} {day}</title>
<style>
 body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 1000px; margin: 2rem auto;
        padding: 0 1rem; color: #1d2b36; }}
 h1 {{ margin-bottom: .2rem; }} .sub {{ color: #6b7a86; margin-top: 0; }}
 .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .8rem; margin: 1.5rem 0; }}
 .kpi {{ background: #f4f6f7; border-radius: 8px; padding: .8rem 1rem; }}
 .kpi .v {{ font-size: 1.35rem; font-weight: 600; }} .kpi .l {{ font-size: .8rem; color: #6b7a86; }}
 .tbl {{ border-collapse: collapse; width: 100%; font-size: .9rem; }}
 .tbl th, .tbl td {{ padding: .35rem .6rem; text-align: right; border-bottom: 1px solid #e3e7ea; }}
 .tbl th:first-child, .tbl td:first-child {{ text-align: left; }}
 .note {{ font-size: .8rem; color: #6b7a86; }}
</style></head><body>
<h1>Battery arbitrage – {zone}, {day}</h1>
<p class="sub">{_fmt(bat.power_mw, 1)} MW / {_fmt(bat.capacity_mwh, 1)} MWh ·
round-trip efficiency {_fmt(bat.round_trip_eff * 100, 0)} % ·
wear cost {_fmt(bat.degradation_eur_per_mwh, 0)} €/MWh discharged ·
max {cap} cycles/day · optimal day-ahead schedule</p>
<div class="kpis">{kpi_html}</div>
<h2>Day-ahead price and optimal schedule</h2>
{_schedule_chart(sched)}
<h2>P&amp;L history</h2>
{_history_chart(log)}
<h2>Cumulative P&amp;L, last 30 days</h2>
{_cumulative_chart(last30)}
<h2>Last 14 days</h2>
{table}
<p class="note">Day-ahead prices are published the afternoon before delivery, so this is the best possible day-ahead
schedule, not a forecast. Excludes reserve markets, intraday re-trading, grid fees and taxes. Data: ENTSO-E Transparency
Platform. Generated {generated} Helsinki time.</p>
</body></html>"""
    config.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (config.DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
