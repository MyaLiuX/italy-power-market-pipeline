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

<!-- TODO: verify the data item codes above against the API guide before publishing. -->
<!-- TODO: record the geographic granularity actually available for each dataset
     (per bidding zone vs national only) once the availability probe has run.
     This determines whether the three datasets share a join grain. -->

## Data engineering challenges

The value of this dataset is that it is not clean. The following are real
properties of the source that the pipeline has to handle.

### Time resolution changes mid-history

The European day-ahead market moved from a 60-minute to a 15-minute market time
unit, going live on the trading day of 30 September 2025 for delivery day
1 October 2025. Historical data therefore contains two different resolutions in
the same series, and any weighted aggregation across that boundary has to account
for the change in interval length.

Demand and generation resolutions are published independently of the price
resolution and are not assumed to switch on the same date.

### Time zones and daylight saving

The API returns timestamps localised to the zone's own time zone
(`Europe/Rome`), where the UTC offset shifts between `+01:00` and `+02:00`.
Local time is not a usable key: the October transition produces a repeated local
hour and the March transition produces a missing one.

The pipeline stores all timestamps in UTC and converts to local time only at the
presentation layer.

### Inclusive query boundaries

The client returns an inclusive `[start, end]` range, so a per-day ingestion loop
receives the first interval of the following day as an extra row. Without
trimming, adjacent days overlap at the boundary and produce duplicate keys
downstream. Ingestion normalises every window to a half-open `[start, end)`
interval.

### A structural break in the price distribution

The Italian day-ahead market operated with a price floor of 0 EUR/MWh for most of
its history, so the distribution is hard-truncated at zero rather than tapering.
That floor was lifted recently — the first sub-zero day-ahead clearing was on
14 October 2026 — so the distribution changes shape partway through the history.
Any statistical treatment of prices has to be aware of which regime a given
period belongs to.

### Bidding zones are not constant over time

The zone configuration changes. Calabria (`IT_CALA`) was separated out of the
southern zone in 2021, so queries for it return nothing before that date, and
several virtual zones were retired in the same reconfiguration. The zone
dimension is modelled with validity periods rather than as a static list.

<!-- TODO: add the exact CALA start date once confirmed from the data. -->

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