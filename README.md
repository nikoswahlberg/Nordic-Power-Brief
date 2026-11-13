# Nordic Power Brief

[![Daily brief](https://github.com/nikoswahlberg/Nordic-Power-Brief/actions/workflows/daily.yml/badge.svg)](https://github.com/nikoswahlberg/Nordic-Power-Brief/actions/workflows/daily.yml)
[![CI](https://github.com/nikoswahlberg/Nordic-Power-Brief/actions/workflows/ci.yml/badge.svg)](https://github.com/nikoswahlberg/Nordic-Power-Brief/actions/workflows/ci.yml)

An automated morning brief for the Finnish power market. Every day at 06:00 Helsinki time a GitHub Actions job
fetches today's day-ahead electricity prices from ENTSO-E, checks them, works out the most a grid battery could earn
by charging when power is cheap and selling when it is expensive, and publishes the result as a web page. No server,
no database: the job, the data log and the page all live in this repository.

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

#### The report

[The live report](https://nikoswahlberg.github.io/Nordic-Power-Brief/) shows, top to bottom:

1. A short plain-language introduction to the brief and the example battery
2. Key figures for today: profit, cycles, captured spread, last-30-day total and its yearly pace
3. Price statistics: lowest, average and highest price of the day
4. Today's day-ahead price with the optimal charge and discharge schedule
5. Cumulative profit over the last 30 days
6. A table of the last 14 days

If the page shows a day other than today after 07:00 Helsinki time, a red banner at the top says the brief is out
of date, so a failed or late run is visible on the page itself.

The brief covers the Finnish bidding zone (FI) only.

## Battery settings

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
pip install -r requirements.txt -r requirements-dev.txt   # exact versions; upgrade on purpose, then run the tests

python -m brief.run --demo          # synthetic prices, no token needed, writes to demo/
open demo/docs/index.html

export ENTSOE_API_TOKEN=...         # real data
python -m brief.run                 # today, plus any missing days of the last 30
python -m brief.run --backfill 2026-10-01 2026-11-10   # a longer history
pytest -q && ruff check .
```

## Set up the daily job

1. Get an ENTSO-E API token: register on the Transparency Platform, then email transparency@entsoe.eu with
   "Restful API access" in the subject line.
2. Add it as a repository secret: Settings → Secrets and variables → Actions → `ENTSOE_API_TOKEN`.
3. Enable Pages: Settings → Pages → Deploy from branch → `main` / `docs`.
4. Nothing to backfill by hand: each run fetches any of the last 30 days missing from `data/`.
5. Actions → *Daily brief* → *Run workflow* to test it. After that it runs on the schedule: 06:00 Helsinki time, summer and winter (cron at 03:00 and 04:00 UTC; the run before 06:00 local time skips itself).

## Repository layout

```
brief/
  config.py     battery settings, bidding zone (FI) and history length
  entsoe.py     API client and XML parser
  validate.py   data checks
  battery.py    optimiser
  store.py      CSV storage
  report.py     HTML report
  run.py        CLI / daily entry point
data/           battery_pnl.csv + per-day schedules (committed by the bot)
docs/           index.html (GitHub Pages)
tests/          optimiser, parser and history-fill tests
```

## Limitations

* Day-ahead only: no FCR/aFRR/mFRR reserve revenue, which in practice makes up most Finnish BESS income.
* Full-power steps only: the battery is either at full power or idle in each interval.
* Excludes grid tariffs, electricity tax and imbalance costs.
* Each day is optimised on its own: the battery starts and ends every day empty, so trades across midnight are
  not counted. On 15 Oct – 13 Nov 2026 optimising across midnight would have added 0.9 % (43 € in 30 days).

## Roadmap

Next:

* Realistic benchmark: compare the best possible result with a simple rule (for example "charge in the cheapest
  2 hours, sell in the dearest 2") and show what share of the maximum it captures
* Price context from Fingrid open data: wind power and consumption, to explain high- and low-profit days
* Price-anomaly flags (negative-price hours, spikes against last week)
* Longer view: monthly totals and a one-year backfill

Later:

* Reserve market revenue (FCR, aFRR, mFRR) from Fingrid open data
* Grid fees and electricity tax
* Battery size comparison (1-, 2- and 4-hour batteries)
* Morning summary by email or Slack, linking to the page
