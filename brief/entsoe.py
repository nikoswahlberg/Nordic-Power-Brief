"""Fetch and parse ENTSO-E day-ahead prices (document type A44).

Day-ahead moved to 15-minute resolution in late 2025, and ENTSO-E uses
curve type A03, which *omits* points whose price equals the previous one.
The parser below forward-fills those gaps, which naive parsers get wrong.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, time, timedelta

import pandas as pd
import requests

from .config import BIDDING_ZONES, LOCAL_TZ

API_URL = "https://web-api.tp.entsoe.eu/api"
_RES = {"PT15M": timedelta(minutes=15), "PT30M": timedelta(minutes=30), "PT60M": timedelta(hours=1)}


def delivery_window_utc(day: date) -> tuple[datetime, datetime]:
    """Local (Helsinki) midnight-to-midnight, expressed in UTC. Handles DST days."""
    start = datetime.combine(day, time(0), tzinfo=LOCAL_TZ)
    end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=LOCAL_TZ)
    return start.astimezone(UTC), end.astimezone(UTC)


def fetch_xml(day: date, zone: str = "FI", token: str | None = None) -> str:
    token = token or os.environ.get("ENTSOE_API_TOKEN")
    if not token:
        raise RuntimeError("Set ENTSOE_API_TOKEN (env var or GitHub secret).")
    start, end = delivery_window_utc(day)
    eic = BIDDING_ZONES[zone]
    params = {
        "securityToken": token,
        "documentType": "A44",
        "in_Domain": eic,
        "out_Domain": eic,
        "periodStart": start.strftime("%Y%m%d%H%M"),
        "periodEnd": end.strftime("%Y%m%d%H%M"),
    }
    r = requests.get(API_URL, params=params, timeout=60)
    r.raise_for_status()
    if "Acknowledgement_MarketDocument" in r.text:
        raise RuntimeError(f"ENTSO-E returned no data for {zone} {day}: {r.text[:300]}")
    return r.text


def parse_prices(xml_text: str) -> pd.Series:
    """Return a price series (EUR/MWh) indexed by UTC interval start."""
    root = ET.fromstring(xml_text)
    ns = {"ns": root.tag.split("}")[0].strip("{")}
    by_res: dict[str, dict[pd.Timestamp, float]] = {}

    for period in root.iterfind(".//ns:TimeSeries/ns:Period", ns):
        res_code = period.findtext("ns:resolution", namespaces=ns)
        step = _RES[res_code]
        start = pd.Timestamp(period.findtext("ns:timeInterval/ns:start", namespaces=ns))
        end = pd.Timestamp(period.findtext("ns:timeInterval/ns:end", namespaces=ns))
        n_slots = int((end - start) / step)

        given = {
            int(p.findtext("ns:position", namespaces=ns)): float(p.findtext("ns:price.amount", namespaces=ns))
            for p in period.iterfind("ns:Point", ns)
        }
        last = None
        out = by_res.setdefault(res_code, {})
        for pos in range(1, n_slots + 1):
            last = given.get(pos, last)  # A03: missing position = same price as before
            if last is not None:
                out[start + (pos - 1) * step] = last

    if not by_res:
        raise ValueError("No price points found in ENTSO-E document")
    finest = min(by_res, key=lambda k: _RES[k])  # prefer 15-min if both are published
    s = pd.Series(by_res[finest], name="price_eur_mwh").sort_index()
    s.index.name = "start_utc"
    return s


def get_day_ahead(day: date, zone: str = "FI") -> pd.Series:
    prices = parse_prices(fetch_xml(day, zone))
    start, end = delivery_window_utc(day)
    return prices[(prices.index >= start) & (prices.index < end)]
