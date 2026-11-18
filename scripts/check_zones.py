"""Show which zones the seed declares active on a few dates."""

from datetime import date
from pathlib import Path

from italy_power_market_pipeline.ingest.zones import active_zones

# Relative to the repo root: run this script from there.
SEED_PATH = Path("seeds/dim_zones.csv")

for iso in ["2020-06-15", "2021-01-01", "2026-11-15"]:
    zones = active_zones(SEED_PATH, date.fromisoformat(iso))
    print(f"{iso}  {len(zones)} zones  {zones}")