from datetime import date

import pandas as pd
import pytest

from brief.entsoe import delivery_window_utc, parse_prices
from brief.validate import check_day_prices

# Trimmed A44 document: one hour at 15-min resolution, curve type A03.
# Position 3 is omitted, meaning it repeats position 2's price.
SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <TimeSeries>
    <curveType>A03</curveType>
    <Period>
      <timeInterval><start>2026-11-10T22:00Z</start><end>2026-11-10T23:00Z</end></timeInterval>
      <resolution>PT15M</resolution>
      <Point><position>1</position><price.amount>41.5</price.amount></Point>
      <Point><position>2</position><price.amount>39.0</price.amount></Point>
      <Point><position>4</position><price.amount>-1.2</price.amount></Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>"""


def test_parse_fills_omitted_a03_points():
    s = parse_prices(SAMPLE)
    assert list(s.values) == [41.5, 39.0, 39.0, -1.2]
    assert s.index[0] == pd.Timestamp("2026-11-10T22:00Z")
    assert s.index[1] - s.index[0] == pd.Timedelta(minutes=15)


def test_window_is_local_midnight_in_utc():
    start, end = delivery_window_utc(date(2026, 11, 11))  # EET = UTC+2
    assert start == pd.Timestamp("2026-11-10T22:00Z")
    assert (end - start) == pd.Timedelta(hours=24)


def test_dst_day_has_23_hours():
    start, end = delivery_window_utc(date(2026, 3, 29))  # clocks go forward
    assert (end - start) == pd.Timedelta(hours=23)


def test_validation_catches_gaps():
    start, _ = delivery_window_utc(date(2026, 11, 11))
    idx = pd.date_range(start, periods=95, freq="15min")  # one interval short
    with pytest.raises(ValueError, match="expected 96"):
        check_day_prices(pd.Series(50.0, index=idx), date(2026, 11, 11))
