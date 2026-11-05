# Data profile — ENTSO-E, Italian bidding zones

Findings from the exploration in `notebooks/`. Everything below was measured
against the live API unless marked otherwise.

Probes run 2026-11-05 with `entsoe-py` 0.8.1.

---

## 1. Geography

### Bidding zones

Seven zones, declared from the GME zone definition and confirmed present in all
three datasets. The zone dimension is a maintained seed file
(`seeds/dim_zone.csv`), not derived from API responses — a zone that stops
returning data is a data quality incident, not a zone that stopped existing.

| Zone | EIC code | valid_from |
|---|---|---|
| IT_NORD | 10Y1001A1001A73I | (before window) |
| IT_CNOR | 10Y1001A1001A70O | (before window) |
| IT_CSUD | 10Y1001A1001A71M | (before window) |
| IT_SUD | 10Y1001A1001A788 | (before window) |
| IT_CALA | 10Y1001C--00096J | 2021-01-01 |
| IT_SICI | 10Y1001A1001A75E | (before window) |
| IT_SARD | 10Y1001A1001A74G | (before window) |

`IT_CALA` returns `NoMatchingDataError` for every probe before 2021-01, and data
from 2021-01 onwards. It was separated out of `IT_SUD` in the 2021 bidding zone
reconfiguration. Before that date `IT_SUD` covered Calabria as well, so the
backfill window starts 2021-01-01 and the zone dimension is static across it.

### Areas that are not bidding zones

Probing every `IT*` member of the `entsoe.mappings.Area` enum:

| Area | price | load | generation | Interpretation |
|---|---|---|---|---|
| `IT` | no data | yes | yes | Control area. No national clearing price is published — PUN is GME's own index and is not on this API. |
| `IT_SACO_AC`, `IT_SACO_DC` | yes | no data | no data | Sardinia–Corsica interconnection virtual zones. |
| 11 others | no data | no data | no data | Retired in the 2021 reconfiguration (`IT_BRNN`, `IT_FOGN`, `IT_PRGP`, `IT_ROSN`, `IT_NORD_AT/CH/FR/SI`, `IT_GR`, `IT_MALTA`, `IT_MACRO_NORTH`, `IT_MACRO_SOUTH`). |

Note the `IT_SACO_*` rows: a price alone does not identify a bidding zone. This
is why the dimension is declared rather than discovered.

### Join grain

**All three datasets are published per bidding zone.** Prices, load and
generation share the same geographic grain, so the fact tables can join directly
without aggregating prices to a national level.

---

## 2. Datasets

| Dataset | entsoe-py method | ENTSO-E document type | Unit |
|---|---|---|---|
| Day-ahead prices | `query_day_ahead_prices` | A44 *(unverified)* | EUR/MWh |
| Actual total load | `query_load` | A65 *(unverified)* | MW |
| Actual generation per production type | `query_generation` | A75 (confirmed, seen in a request URL) | MW |

Values are **power in MW**, not energy in MWh. This decides the upsampling rule:
an hourly value becomes four identical quarter-hourly values, never a value
divided by four.

---

## 3. Time resolution — two separate switches

The 60-minute to 15-minute transition did **not** happen on one date for all
three datasets.

| Dataset | Switched | Evidence |
|---|---|---|
| Load, generation | **2024-12-31 at 01:00 local (00:00 UTC)** | 2024-12-30 hourly; 2024-12-31 returns 93 rows |
| Day-ahead prices | **2025-10-01** (SDAC delivery day) | 2025-09-25 hourly; 2025-10-05 15-minute |

### The load/generation switch happens mid-day

2024-12-31 returns 93 rows, not 96. The index explains it:

```
delta counts:
0 days 00:15:00    91
0 days 01:00:00     1

2024-12-31 00:00:00+01:00    11071.0
2024-12-31 01:00:00+01:00    10322.0
2024-12-31 01:15:00+01:00    10322.0
...
```

One hourly interval covering 00:00–01:00, then 92 quarter-hourly rows. The
switch is aligned to **UTC midnight**, not to local midnight.

Consequence: resolution cannot be decided per day. On the boundary day a single
response carries both resolutions, so the ingestion layer must read the
resolution from the row spacing, not from the date.

All seven zones behave identically on this date (93 rows, 15-minute modal step),
so this is market-wide, not a property of one zone.

### Open: the price switch has not been examined at row level

The price switch is known to the day but has not been checked for the same
mid-day behaviour. Worth probing 2025-09-30 and 2025-10-01 before writing the
ingestion logic.

---

## 4. Query boundaries differ per dataset

On a normal 24-hour day at 15-minute resolution:

| Dataset | Rows | Interval |
|---|---|---|
| Day-ahead prices | 97 | inclusive `[start, end]` |
| Actual total load | 96 | half-open `[start, end)` |
| Actual generation | 96 | half-open `[start, end)` |

Prices return one extra row belonging to the following day. A per-day ingestion
loop that does not trim it produces overlapping days and duplicate keys.

**The same trimming rule cannot be applied to all three.** Trimming uniformly
would silently drop one interval per day from load and generation.

---

## 5. Time zone and DST

The API returns a tz-aware index localised to `Europe/Rome`, with the offset
shifting between `+01:00` and `+02:00`.

### Local time is not a valid key

On 2025-10-26 the clock falls back and local time 02:00 occurs twice, with
different prices:

```
local   offset   utc     price
02:00   +02:00   00:00   92.83
02:15   +02:00   00:15   90.90
02:30   +02:00   00:30   84.09
02:45   +02:00   00:45   75.34
02:00   +01:00   01:00   82.34   <- local 02:00 again
02:15   +01:00   01:15   90.78
```

The UTC column is contiguous and unique; the local column is not. All timestamps
are stored in UTC and converted to local time only for presentation.

The repeated hour is published in full — both passes are present, and the index
has no holes.

### Date arithmetic must be calendar-aware

`pd.Timedelta(days=1)` is an absolute 24 hours and is wrong on DST days:

| Day | `Timedelta(days=1)` | `DateOffset(days=1)` | Correct |
|---|---|---|---|
| 2025-10-26 (25h) | 24.0 h — loses the last hour | 25.0 h | DateOffset |
| 2025-03-30 (23h) | 24.0 h — reaches into the next day | 23.0 h | DateOffset |
| ordinary day | 24.0 h | 24.0 h | either |

October under-fetches by an hour; March over-fetches by an hour and overlaps the
following day. Twelve days are affected across a six-year backfill, and the
other ~2,180 days look perfectly normal — this fails silently.

With `DateOffset`, 2025-10-26 returns 101 rows spanning 25.0 hours, matching the
inclusive-boundary expectation for prices. All seven zones return 101.

---

## 6. Generation table structure

`query_generation` returns a wide table with a two-level column MultiIndex:
production type, and `Actual Aggregated` / `Actual Consumption`.

### Column count varies by zone

| Zone | Columns |
|---|---|
| IT_NORD | 14 |
| IT_CSUD | 13 |
| IT (national) | 13 |
| IT_SARD | 12 |
| IT_SICI | 12 |
| IT_CNOR | 10 |
| IT_SUD | 10 |
| IT_CALA | 6 |

`IT_SARD`'s production types are a strict subset of `IT_NORD`'s. The difference
is `Fossil Gas` and `Hydro Pumped Storage / Actual Consumption`. Sardinia having
no gas-fired generation matches the physical system — the island is not
connected to the national gas grid.

Note that the national `IT` area is not a superset of the zones: it has 13
columns while `IT_NORD` alone has 14.

**The wide format cannot be unified into one table.** Generation is unpivoted to
long format: `(timestamp, zone, production_type, measure, value_mw)`.

### Two different kinds of absence

| Observed | Meaning | In long format |
|---|---|---|
| Column not present for the zone | The zone has no such generation type | No row |
| Column present, value is `NaN` | The type exists but was not reported for that interval | Row with NULL value |

`IT_SARD` on 2026-11-01 has no fully-null columns. Its NaNs are concentrated in
`Energy storage`: 58 of 96 intervals null for `Actual Aggregated`, 38 of 96 for
`Actual Consumption`. That is intermittent reporting, not an absent type, and
must not be collapsed to zero — doing so corrupts any share-of-total
calculation.

### The production type list grows over time

| Probe date | Columns (IT_NORD) |
|---|---|
| 2016-06-15, 2018-06-15 | 11 |
| 2020-06-15 … 2024-06-15 | 13 |
| 2026-06-15 | 14 |

The source schema evolves. `Energy storage` is a recent addition. A fixed column
list would break on backfill; long format absorbs this without a schema change.

---

## 7. API behaviour

### Transient 599 errors

The API returns a non-standard HTTP 599 on server-side failures, at random. In a
single exploration run, the same request (load for IT_NORD on 2026-11-01)
succeeded in one block and failed in another.

Ingestion retries with exponential backoff. `NoMatchingDataError` is a real
answer and is never retried.

### Credentials appear in the URL

The API key is passed as a `securityToken` query parameter, so it appears in
request URLs and therefore in any traceback or log. Logs containing raw
tracebacks must not be committed.

### Rate limit

400 requests per minute.

---

## 8. Price distribution

*From published sources, not yet verified against the data.*

The Italian day-ahead market operated with a price floor of 0 EUR/MWh for most
of its history, so prices are hard-truncated at zero rather than tapering. The
first sub-zero day-ahead clearing was on 2026-10-14, when the three southern
zones settled at −0.01 EUR/MWh while IT_NORD cleared above 160 EUR/MWh in the
same quarter-hour.

Any statistical treatment of prices has to account for which regime a period
belongs to. **To verify in the data:** count prices at exactly 0 and below 0, by
zone and year.

---

## 9. Open questions

1. **Does the price switch also happen mid-day?** Probe 2025-09-30 and
   2025-10-01 at row level, as was done for load.
2. **Is the source itself upsampling?** On 2024-12-31 the four quarter-hourly
   load values at 01:00–01:45 are bit-identical (10322.0). Real load does not
   hold a constant for 45 minutes. If the source repeated an hourly value
   without marking it, some "15-minute" data is synthetic at origin. Check by
   counting consecutive identical values on that day against an ordinary day.
3. **Is `Actual Total Load` measured net of distributed generation?** Rooftop PV
   connected behind the meter would appear as reduced load rather than as
   generation, which would systematically understate solar share. Needs the
   ENTSO-E definition of Total Load.
4. **Document type codes for prices and load** are unverified; only A75
   (generation) has been confirmed from a request URL.
5. **Cross-zonal transfer capacity** (Forecasted Transfer Capacities 11.1,
   Scheduled Commercial Exchanges 12.1.F) was identified as the dataset needed
   to explain price separation between zones, but is out of scope for the
   current three-dataset model.