# Nordic Power Brief

[![Daily brief](https://github.com/nikoswahlberg/Nordic-Power-Brief/actions/workflows/daily.yml/badge.svg)](https://github.com/nikoswahlberg/Nordic-Power-Brief/actions/workflows/daily.yml)
[![CI](https://github.com/nikoswahlberg/Nordic-Power-Brief/actions/workflows/ci.yml/badge.svg)](https://github.com/nikoswahlberg/Nordic-Power-Brief/actions/workflows/ci.yml)

An automated morning brief for the Finnish power market. Every day at about 08:00 Helsinki time a GitHub Actions job
pulls the day-ahead prices from ENTSO-E, validates them, works out how a grid battery should have traded them, and
publishes a report.

**Live report:** https://nikoswahlberg.github.io/Nordic-Power-Brief/

## Module 1: battery arbitrage P&L

For each delivery day: what is the most a 1 MW / 2 MWh battery can earn by buying and selling in the FI day-ahead
market, after efficiency losses, wear cost and a daily cycle limit?

Day-ahead prices are published around midday the day before delivery, so this is not a forecast. It is the best
achievable day-ahead schedule, and the daily log gives a running benchmark of what simple arbitrage is worth in
Finland.

### How it works

```
ENTSO-E API ─► parse (15-min, A03 gap-fill) ─► validate ─► optimise (DP) ─► CSV log ─► HTML report ─► GitHub Pages
                                                  │
                                    fails loudly = red run = alert
```

* **Exact optimisation, not a heuristic.** Dynamic programming over the state of charge and discharge steps used,
  96 quarter-hours × 9 SoC levels × cycle budget. Each interval: charge at full power, idle, or discharge.
  A test compares it with brute force over every possible action sequence.
* **Realistic costs.** Round-trip efficiency is split evenly between charging and discharging, plus a wear cost per
  MWh discharged and a daily cycle cap. Negative prices pay the battery to charge.
* **Correct parsing.** Since the move to 15-minute day-ahead products, ENTSO-E sends curve type A03, which leaves
  out points whose price did not change. The parser forward-fills them; parsing points naively silently loses
  intervals.
* **DST-safe.** Delivery days are local Helsinki days, so days have 92, 96 or 100 quarter-hours.
* **Validation as alerting.** Missing intervals, duplicates or prices outside the SDAC limits (−500 to 4 000 €/MWh)
  make the job fail, and GitHub emails the failure.

### Battery settings

Change them in [`brief/config.py`](brief/config.py):

| Setting | Default |
|---|---|
| Power | 1 MW |
| Usable capacity | 2 MWh |
| Round-trip efficiency | 88 % |
| Wear cost | 5 €/MWh discharged |
| Max cycles per day | 2 |

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

python -m brief.run --demo          # synthetic prices, no token needed, writes to demo/
open demo/docs/index.html

export ENTSOE_API_TOKEN=...         # real data
python -m brief.run --backfill 2026-10-01 2026-11-10
python -m brief.run                 # today
pytest -q && ruff check .
```

## Set up the daily job

1. Get an ENTSO-E API token: register on the Transparency Platform, then email transparency@entsoe.eu with
   "Restful API access" in the subject line.
2. Add it as a repository secret: Settings → Secrets and variables → Actions → `ENTSOE_API_TOKEN`.
3. Enable Pages: Settings → Pages → Deploy from branch → `main` / `docs`.
4. Run the backfill once locally and commit `data/`, so the history chart starts full.
5. Actions → *Daily brief* → *Run workflow* to test it. After that it runs on the schedule (05:30 UTC).

## Repository layout

```
brief/
  config.py     battery and bidding zone settings
  entsoe.py     API client and XML parser
  validate.py   data checks
  battery.py    optimiser
  store.py      CSV storage
  report.py     HTML report
  run.py        CLI / daily entry point
data/           battery_pnl.csv + per-day schedules (committed by the bot)
docs/           index.html (GitHub Pages)
tests/
```

## Limitations

* Day-ahead only: no FCR/aFRR/mFRR reserve revenue, which in practice makes up most Finnish BESS income.
* Full-power steps only: the battery is either at full power or idle in each interval.
* Excludes grid tariffs, electricity tax and imbalance costs.

## Roadmap

* FI–SE1 / FI–EE spread and price-decoupling section
* Price-anomaly flags (negative-price hours, spikes against last week)
* Reserve market prices from Fingrid open data
