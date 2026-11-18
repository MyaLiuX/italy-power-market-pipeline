"""Extract one delivery day of all datasets for all active Italian zones.

Usage, from the repo root:
    uv run python scripts/extract_one_day.py 2026-11-15

Exits with status 1 if any zone did not return data, so a scheduler
can tell a partial day from a complete one.
"""

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from italy_power_market_pipeline.ingest.client import make_client
from italy_power_market_pipeline.ingest.extract import extract_day

# Both paths are relative to the repo root.
SEED_PATH = Path("seeds/dim_zones.csv")
OUT_DIR = Path("data/raw")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("delivery_date", type=date.fromisoformat, help="YYYY-MM-DD")
    args = parser.parse_args()

    # INFO, never DEBUG: at DEBUG level entsoe-py logs the API key.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    load_dotenv()
    api_key = os.environ.get("ENTSOE_API_KEY")
    if not api_key:
        sys.exit("ENTSOE_API_KEY is not set - check that .env sits in the repo root")

    result = extract_day(args.delivery_date, make_client(api_key), SEED_PATH, OUT_DIR)

    # Manifest: one line per dataset and zone, then the files written.
    print("\n--- manifest ---")
    for z in result.zones:
        print(f"{z.dataset:<18} {z.zone:<8} {z.status:<8} {z.rows:>5}  {z.detail}")
    print("\n--- files ---")
    for path in result.files:
        print(path)

    if not result.all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()