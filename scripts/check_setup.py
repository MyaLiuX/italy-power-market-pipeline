"""Verify the local setup before any data exploration starts.

Checks three things that would otherwise surface later disguised as data problems:
  1. The interpreter resolves to this repo's .venv
  2. The API key is actually loaded from .env
  3. The installed entsoe-py signatures match what we plan to call

Run with: uv run python scripts/check_setup.py
"""

import inspect
import os
import sys

import entsoe
import pandas as pd
from dotenv import load_dotenv
from entsoe import EntsoePandasClient

# --- 1. Environment ---------------------------------------------------------
print("python     :", sys.executable)
print("entsoe-py  :", entsoe.__version__)
print("pandas     :", pd.__version__)

# --- 2. Credentials ---------------------------------------------------------
# load_dotenv() reads .env from the current working directory upwards.
# Run this script from the repo root so it finds the right one.
load_dotenv()
api_key = os.getenv("ENTSOE_API_KEY")
assert api_key, "ENTSOE_API_KEY not found - check that .env sits in the repo root"
print("api key    : loaded, length", len(api_key))

client = EntsoePandasClient(api_key=api_key)

# --- 3. API signatures ------------------------------------------------------
# entsoe-py changed its interface around the 15-minute MTU switch.
# Trust the installed version's signature, not online examples.
for method_name in ("query_day_ahead_prices", "query_load", "query_generation"):
    signature = inspect.signature(getattr(client, method_name))
    print(f"\n{method_name}{signature}")

# --- 4. Connectivity smoke test ---------------------------------------------
# One zone, one day. The goal is a successful round trip, not useful data.
# entsoe-py requires tz-aware timestamps; naive ones raise.
start = pd.Timestamp("2026-11-01", tz="Europe/Rome")
end = pd.Timestamp("2026-11-03", tz="Europe/Rome")

prices = client.query_day_ahead_prices("IT_NORD", start=start, end=end)

print("\n--- IT_NORD day-ahead price, 2026-11-01 ---")
print("type   :", type(prices))
print("shape  :", prices.shape)
print("tz     :", prices.index.tz)
print("dtype  :", prices.dtype)
print(prices.head(5))

# Time deltas between consecutive timestamps reveal the actual resolution.
# Counting rows and dividing would hide gaps and duplicates.
print("\nobserved time deltas:")
print(prices.index.to_series().diff().value_counts())