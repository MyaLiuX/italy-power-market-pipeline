"""Measure how long one request takes as the window grows.

Single-day probes showed about 50s for prices and 15-20s for load and
generation. Prices return the least data and take the longest, which suggests
the cost is mostly fixed per request rather than proportional to the data
returned. If that holds, a large window costs little more than a small one,
and the backfill's request count falls by the same factor.

Usage, from the repo root:
    uv run python scripts/check_chunk_size.py

Nothing is written: this only times requests and reports interval counts.
"""

import os
import time
from datetime import date

from dotenv import load_dotenv
from entsoe import EntsoePandasClient

from italy_power_market_pipeline.ingest.timewindow import day_window_utc

ZONE = "IT_NORD"  # the most production types, so the heaviest generation response

# ENTSO-E times out server-side after 300s, so waiting longer is pointless.
TIMEOUT_SECONDS = 300

WINDOWS = [
    ("1 day    2023-01-18", date(2023, 1, 18), date(2023, 1, 18)),
    ("1 month  2023-01",    date(2023, 1, 1),  date(2023, 1, 31)),
    ("1 year   2023",       date(2023, 1, 1),  date(2023, 12, 31)),
    ("1 month  2026-01",    date(2026, 1, 1),  date(2026, 1, 31)),  # 15-minute data
]


def main() -> None:
    load_dotenv()
    api_key = os.environ.get("ENTSOE_API_KEY")
    if not api_key:
        raise SystemExit("ENTSOE_API_KEY is not set")

    # A client of its own, with a long timeout: the point is to find out how
    # long a large window actually takes, not to respect the pipeline's limit.
    client = EntsoePandasClient(api_key=api_key, retry_count=1, timeout=TIMEOUT_SECONDS)
    queries = {
        "prices": client.query_day_ahead_prices,
        "load": client.query_load,
        "generation": client.query_generation,
    }

    for label, first_day, last_day in WINDOWS:
        start, _ = day_window_utc(first_day)
        _, end = day_window_utc(last_day)
        print(f"\n{label}   {start} -> {end}")
        for name, query in queries.items():
            began = time.perf_counter()
            try:
                raw = query(ZONE, start=start, end=end)
                print(f"  {name:<11} {time.perf_counter() - began:6.1f}s  "
                      f"{len(raw.index):>6} intervals")
            except Exception as exc:
                print(f"  {name:<11} {time.perf_counter() - began:6.1f}s  "
                      f"FAILED  {type(exc).__name__}")


if __name__ == "__main__":
    main()