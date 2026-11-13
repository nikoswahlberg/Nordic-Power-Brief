"""Render docs/index.html (served by GitHub Pages)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

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


def _num(x) -> str:
    """Plain number for running text: no decimals when it is a whole number."""
    return _fmt(x, 0 if float(x).is_integer() else 1)


def _intro(bat: Battery) -> str:
    cycles = (f"can be fully charged at most {_num(bat.max_cycles_per_day)} times a day"
              if bat.max_cycles_per_day else "has no daily limit on how often it is charged")
    return (
        "Every morning this brief works out the most a grid battery in Finland could earn today by charging when "
        "electricity is cheap and selling it back when it is expensive. It uses today's Finnish electricity prices, "
        f"which are set the day before. The example battery charges and discharges at up to {_num(bat.power_mw)} "
        f"megawatt and stores {_num(bat.capacity_mwh)} megawatt-hours. It loses "
        f"{_num(round((1 - bat.round_trip_eff) * 100, 1))} % of the energy it stores, counts "
        f"{_num(bat.degradation_eur_per_mwh)} € of wear for every megawatt-hour it sells, and {cycles}."
    )


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
    window_start = (day - timedelta(days=config.HISTORY_DAYS - 1)).isoformat()
    last30 = log[(log["date"] >= window_start) & (log["date"] <= day.isoformat())]
    annualised_per_mw = last30["pnl_eur"].mean() * 365 / bat.power_mw if len(last30) else None
    spread = (summary["avg_sell_price"] - summary["avg_buy_price"]) if summary["avg_sell_price"] else None

    kpis = [
        ("P&L for the day", _fmt(summary["pnl_eur"], 0, "€")),
        ("Cycles", _fmt(summary["cycles"], 2)),
        ("Captured spread", _fmt(spread, 1, "€/MWh")),
        ("Last 30 days", _fmt(last30["pnl_eur"].sum(), 0, "€")),
        ("30-day pace, €/MW/year", _fmt(annualised_per_mw, 0)),
    ]
    prices = [
        ("Lowest price", _fmt(summary["price_min"], 1, "€/MWh")),
        ("Average price", _fmt(summary["price_avg"], 1, "€/MWh")),
        ("Highest price", _fmt(summary["price_max"], 1, "€/MWh")),
    ]

    def cards(items):
        return "".join(f'<div class="kpi"><div class="v">{v}</div><div class="l">{k}</div></div>' for k, v in items)

    table = (
        log.tail(14).iloc[::-1][["date", "pnl_eur", "cycles", "avg_buy_price", "avg_sell_price", "negative_intervals"]]
        .rename(columns={"date": "Date", "pnl_eur": "P&L €", "cycles": "Cycles", "avg_buy_price": "Avg buy €/MWh",
                         "avg_sell_price": "Avg sell €/MWh", "negative_intervals": "Neg. price intervals"})
        .to_html(index=False, border=0, classes="tbl", na_rep="–",
                 float_format=lambda x: f"{x:,.2f}".replace(",", " ").replace(".", ","))
    )
    generated = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daily brief: battery arbitrage in Finland – {day}</title>
<style>
 body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 1000px; margin: 2rem auto;
        padding: 0 1rem; color: #1d2b36; }}
 h1 {{ margin-bottom: .2rem; }} .sub {{ color: #6b7a86; margin-top: 0; }}
 .intro {{ line-height: 1.5; max-width: 70ch; }}
 .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .8rem; margin: 1.5rem 0; }}
 .kpi {{ background: #f4f6f7; border-radius: 8px; padding: .8rem 1rem; }}
 .kpi .v {{ font-size: 1.35rem; font-weight: 600; }} .kpi .l {{ font-size: .8rem; color: #6b7a86; }}
 .tbl {{ border-collapse: collapse; width: 100%; font-size: .9rem; }}
 .tbl th, .tbl td {{ padding: .35rem .6rem; text-align: right; border-bottom: 1px solid #e3e7ea; }}
 .tbl th:first-child, .tbl td:first-child {{ text-align: left; }}
 .note {{ font-size: .8rem; color: #6b7a86; }}
</style></head><body>
<h1>Daily brief: battery arbitrage in Finland</h1>
<p class="sub">{day.strftime("%A")} {day.day} {day.strftime("%B %Y")}</p>
<p class="intro">{_intro(bat)}</p>
<div class="kpis">{cards(kpis)}</div>
<h2>Price statistics</h2>
<div class="kpis">{cards(prices)}</div>
<h2>Day-ahead price and optimal schedule</h2>
{_schedule_chart(sched)}
<h2>Cumulative P&amp;L, last {config.HISTORY_DAYS} days</h2>
{_cumulative_chart(last30)}
<h2>Last 14 days</h2>
{table}
<p class="note">Day-ahead prices are published the afternoon before delivery, so this is the best possible day-ahead
schedule, not a forecast. Excludes reserve markets, intraday re-trading, grid fees and taxes. Data: ENTSO-E Transparency
Platform. Generated {generated} Helsinki time.</p>
</body></html>"""
    config.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (config.DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
