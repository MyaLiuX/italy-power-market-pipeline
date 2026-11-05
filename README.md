# Italy Power Market Pipeline

An end-to-end data pipeline for the Italian electricity market: ingests day-ahead
prices, electricity demand and generation mix from the ENTSO-E Transparency
Platform, and models them into a BigQuery star schema for analysis.

## Problem

Italy splits its electricity market into seven price zones, and each zone forms
its own price every 15 minutes. The gap between zones can be extreme: on
14 October 2026, three southern zones cleared below zero while the North cleared
above 160 EUR/MWh in the same quarter-hour.

This pipeline consolidates prices, demand and generation mix into a single
warehouse so that one question can be answered consistently: **where, when, and
why does the price look the way it does.**

## Questions this pipeline answers

1. **Where and when** — which zones and which times of day see the highest and
   lowest prices, and how stable is that pattern?
2. **Why** — what drives the differences between zones: demand levels, or a
   shift in what is generating the electricity?
3. **Trend** — are these patterns getting stronger or weaker over time?

## Who this is for

The same data serves both sides of the market:

| Role | Their question | What they decide |
|---|---|---|
| Sellers (generation owners) | When does my output reach the market, and what is the price at that moment? | Where to build, how to price long-term contracts |
| Buyers (large consumers) | When do I draw power, and what does it cost then? | Production scheduling, procurement terms |

Three levels of consumption, which is what the layered architecture is built for:

- **Analysts** — a self-serve dashboard refreshed daily, watching for anomalies
- **Decision makers** — monthly review plus ad-hoc queries against the warehouse
- **Management** — a quarterly summary of exposure

## Data sources

All data comes from the [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/),
accessed through the [`entsoe-py`](https://github.com/EnergieID/entsoe-py) client.

| Dataset | ENTSO-E data item | Role in the model |
|---|---|---|
| Day-ahead prices | 12.1.D | The outcome — what the market cleared at |
| Actual total load | 6.1.A | Demand side |
| Actual generation per production type | 16.1.B&C | Supply side, broken down by fuel |


## Data engineering challenges

The source is not clean. These are measured properties, documented in full
in [docs/data_profile.md](docs/data_profile.md).

- **Two separate resolution switches.** Load and generation moved to 15
  minutes on 2024-12-31; day-ahead prices on 2025-10-01. The load switch
  happens mid-day, so a single response carries both resolutions.
- **Query boundaries differ per dataset.** Prices return an inclusive
  range, load and generation a half-open one. One trimming rule for all
  three silently drops an interval a day.
- **Calendar-aware date arithmetic.** `Timedelta(days=1)` is wrong on the
  two DST days a year — short by an hour in October, overlapping the next
  day in March.
- **Generation schema varies by zone and over time.** Column counts range
  from 6 to 14 and have grown since 2016, so generation is stored long
  rather than wide.
- **Transient 599 errors.** The same request can fail and then succeed, so
  ingestion retries with backoff.

## Architecture

<!-- TODO: add architecture diagram -->

| Layer | Tool |
|---|---|
| Infrastructure | Terraform |
| Ingestion | Python (`entsoe-py`) |
| Orchestration | Airflow |
| Storage (raw) | Google Cloud Storage |
| Transformation | Spark |
| Warehouse | BigQuery (star schema) |
| Visualisation | Power BI |

## Data model

<!-- TODO: fill in once the availability probe confirms the join grain.
     Fact table grain depends on whether load and generation are published
     per bidding zone or only at national level. -->

## Repository layout

```
.
├── scripts/      One-off scripts: setup checks, data probes
├── notebooks/    Exploratory analysis, outputs preserved
├── docs/         Data profile and supporting evidence
├── data/         Raw landing zone (gitignored)
└── .env.example  Required environment variables
```

## Setup

```bash
uv sync
cp .env.example .env     # add your ENTSO-E API key
uv run python scripts/check_setup.py
```

An API key is requested by registering at the ENTSO-E Transparency Platform and
emailing `transparency@entsoe.eu`.