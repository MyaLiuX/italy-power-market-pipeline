"""Extract and publish one delivery day, or a range of days.

Usage, from the repo root:
    uv run python scripts/ingest.py 2026-11-15                   # one day
    uv run python scripts/ingest.py 2026-11-01 --to 2026-11-15   # a range

Exits non-zero if any day was not published, so a scheduler can tell a
complete run from a partial one.
"""

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from italy_power_market_pipeline.ingest.client import make_client
from italy_power_market_pipeline.ingest.run import run_range
from italy_power_market_pipeline.ingest.storage import open_bucket

# Both paths are relative to the repo root.
SEED_PATH = Path("seeds/dim_zones.csv")
OUT_DIR = Path("data/raw")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "start", type=date.fromisoformat, help="first delivery date, YYYY-MM-DD"
    )
    parser.add_argument(
        "--to",
        type=date.fromisoformat,
        dest="end",
        help="last delivery date, inclusive. Defaults to the start date.",
    )
    args = parser.parse_args()
    end = args.end or args.start
    if end < args.start:
        sys.exit("--to must not be earlier than the start date")

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
    project_id = os.environ.get("GCP_PROJECT_ID")
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not project_id or not bucket_name:
        sys.exit("GCP_PROJECT_ID and GCS_BUCKET_NAME are not set - check .env")

    bucket = open_bucket(project_id, bucket_name)
    outcomes = run_range(
        args.start, end, make_client(api_key), bucket, SEED_PATH, OUT_DIR
    )

    # One line per day. The per-zone detail and the gs:// URIs written are
    # already in the log output above, so neither is repeated here.
    print("\n--- summary ---")
    for outcome in outcomes:
        print(f"{outcome.delivery_date}  {outcome.status:<11} {outcome.detail}")

    published = sum(outcome.status == "published" for outcome in outcomes)
    print(f"\n{published} of {len(outcomes)} day(s) published")
    if published != len(outcomes):
        # Non-zero exit: a scheduler must see a partial run as a failure.
        sys.exit(1)


if __name__ == "__main__":
    main()