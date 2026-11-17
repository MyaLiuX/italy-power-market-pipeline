"""Make two real requests through the client wrapper."""

import os
import time
from datetime import date

from dotenv import load_dotenv
from entsoe.exceptions import NoMatchingDataError

from italy_power_market_pipeline.ingest.client import call_with_retry, make_client
from italy_power_market_pipeline.ingest.timewindow import day_window_utc

load_dotenv()
client = make_client(os.environ["ENTSOE_API_KEY"])

zone = "IT_NORD"
start, end = day_window_utc(date(2026, 11, 15))

# One entry per dataset: a label and the client method that fetches it.
datasets = {
    "prices": client.query_day_ahead_prices,
    "load": client.query_load,
    "generation": client.query_generation,
}

for name, query in datasets.items():
    t0 = time.perf_counter()
    data = call_with_retry(lambda: query(zone, start=start, end=end), f"{name} {zone}")
    seconds = time.perf_counter() - t0
    # Prices come back as a Series (one dimension), the others as DataFrames.
    n_cols = 1 if data.ndim == 1 else data.shape[1]
    print(
        f"{name:<10} {seconds:5.1f}s  rows={len(data)}  cols={n_cols}  "
        f"first={data.index[0]}  last={data.index[-1]}"
    )

# A zone that did not exist yet: should fail at once, without retries.
t0 = time.perf_counter()
start, end = day_window_utc(date(2020, 6, 15))
try:
    call_with_retry(
        lambda: client.query_day_ahead_prices("IT_CALA", start=start, end=end),
        "prices IT_CALA",
    )
except NoMatchingDataError:
    print(f"IT_CALA    {time.perf_counter() - t0:5.1f}s  no data, no retries")