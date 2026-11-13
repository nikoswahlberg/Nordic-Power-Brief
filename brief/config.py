"""Central settings. Change the battery or bidding zone here."""

from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"

LOCAL_TZ = ZoneInfo("Europe/Helsinki")

# ENTSO-E EIC code per bidding zone. The brief covers Finland only.
BIDDING_ZONES = {
    "FI": "10YFI-1--------U",
}


@dataclass(frozen=True)
class Battery:
    power_mw: float = 1.0               # max charge/discharge power
    capacity_mwh: float = 2.0           # usable energy
    round_trip_eff: float = 0.88        # AC-to-AC
    degradation_eur_per_mwh: float = 5.0  # wear cost charged on every MWh discharged
    max_cycles_per_day: float | None = 2.0  # warranty-style cap; None = unlimited

    @property
    def one_way_eff(self) -> float:
        return self.round_trip_eff ** 0.5


DEFAULT_ZONE = "FI"
HISTORY_DAYS = 30  # days kept filled in the P&L log and shown in the cumulative chart
DEFAULT_BATTERY = Battery()
