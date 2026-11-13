from datetime import date

import pandas as pd

from brief.run import missing_days


def test_missing_days_lists_only_unlogged_days_for_the_zone():
    log = pd.DataFrame({"date": ["2026-11-10", "2026-11-12", "2026-11-11"], "zone": ["FI", "FI", "SE1"]})
    assert missing_days(log, "FI", date(2026, 11, 10), date(2026, 11, 13)) == [date(2026, 11, 11), date(2026, 11, 13)]


def test_missing_days_on_empty_log():
    days = missing_days(pd.DataFrame(), "FI", date(2026, 11, 1), date(2026, 11, 2))
    assert days == [date(2026, 11, 1), date(2026, 11, 2)]
